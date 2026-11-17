// The claude-speaks overlay: a glass bar with one status light per Claude session. It opens into
// a panel with names and titles under the mouse, and shows a speech bubble with a voice wave
// while a session talks. It only draws what the hub tells it to and reports hotkeys.
// Protocol: one JSON object per line.
// In on stdin: config, state, flash, wave, request, banner, keys, mode, move, peek, bounds, quit.
// Out on stdout: ready, hotkey, mode, moved, bounds, error.
// Built with the C# compiler that ships with Windows (csc.exe of .NET Framework 4) or, failing
// that, by Windows PowerShell 5.1 (Add-Type). Both stop at C# 5, and the file is kept ASCII.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Threading;

namespace ClaudeSpeaks
{
    static class Ui
    {
        static readonly Stopwatch watch = Stopwatch.StartNew();
        public static double Now { get { return watch.Elapsed.TotalSeconds; } }

        public static readonly FontFamily Symbols = new FontFamily("Segoe UI Symbol");
        public static readonly Color Amber = Color.FromRgb(0xFF, 0xB3, 0x00);
        public static readonly Brush Dim = Paint("#C8FFFFFF"), Faint = Paint("#8CFFFFFF");

        // Shape differs as well as color (see Orb), so a state reads without color vision.
        public static Color Tint(string state)
        {
            switch (state)
            {
                case "working": return Color.FromRgb(0x4F, 0xC3, 0xF7);
                case "needs_you": return Amber;
                case "done": return Color.FromRgb(0x66, 0xBB, 0x6A);
                case "failed": return Color.FromRgb(0xEF, 0x53, 0x50);
                default: return Color.FromRgb(0xB0, 0xB6, 0xC0);
            }
        }

        public static Brush Paint(string hex)
        {
            var brush = (Brush)new BrushConverter().ConvertFromInvariantString(hex);
            brush.Freeze();
            return brush;
        }

        public static SolidColorBrush Alpha(Color c, double a)
        {
            return new SolidColorBrush(Color.FromArgb((byte)(255 * Math.Max(0, Math.Min(1, a))), c.R, c.G, c.B));
        }

        public static Pen Line(Color c, double a, double width)
        {
            var pen = new Pen(Alpha(c, a), width);
            pen.StartLineCap = pen.EndLineCap = PenLineCap.Round;
            pen.LineJoin = PenLineJoin.Round;
            return pen;
        }

        static Brush Gradient(Point from, Point to, params string[] stops)
        {
            var brush = new LinearGradientBrush { StartPoint = from, EndPoint = to };
            for (int i = 0; i < stops.Length; i++)
                brush.GradientStops.Add(new GradientStop((Color)ColorConverter.ConvertFromString(stops[i]), i / (double)(stops.Length - 1)));
            brush.Freeze();
            return brush;
        }

        // Dark smoked glass: enough tint that white text stays readable over a bright page.
        public static Brush GlassFill(string kind)
        {
            if (kind == "solid") return Gradient(new Point(0, 0), new Point(0, 1), "#FF2B303A", "#FF14171D");
            if (kind == "none") return Gradient(new Point(0, 0), new Point(0, 1), "#EB2B303A", "#EB14171D");
            return Gradient(new Point(0, 0), new Point(0, 1), "#8C3A4150", "#A612151B");
        }

        public static readonly Brush GlassEdge = Gradient(new Point(0, 0), new Point(1, 1), "#99FFFFFF", "#2EFFFFFF", "#52FFFFFF");
        public static readonly Brush AmberEdge = Paint("#FFFFB300");
    }

    // How loud the voice is over time. The hub listens to the speakers while a line plays and
    // sends the loudness a few values at a time; this keeps the last seconds of it.
    class Wave
    {
        readonly List<double> times = new List<double>(), levels = new List<double>();
        double step = 0.04;
        public const double Lag = 0.05;  // drawn this far behind, so the newest value has arrived
        public bool Synthetic;  // the hub cannot hear the voice, so make up a plausible motion
        public double Since = double.MaxValue;  // when the current line started

        public void Add(double start, double every, double[] values)
        {
            step = every;
            int old = 0;
            while (old < times.Count && times[old] < Ui.Now - 6) old++;
            times.RemoveRange(0, old);
            levels.RemoveRange(0, old);
            // Values arrive in small bursts; line them up one after another so the motion is even.
            if (times.Count > 0 && start < times[times.Count - 1] + step) start = times[times.Count - 1] + step;
            for (int i = 0; i < values.Length; i++) { times.Add(start + i * step); levels.Add(values[i]); }
        }

        public void Clear() { times.Clear(); levels.Clear(); Since = double.MaxValue; }

        public double At(double t)
        {
            if (Synthetic)
            {
                if (t < Since) return 0;
                double syllable = Math.Abs(Math.Sin(t * 9.1)) * (0.55 + 0.45 * Math.Sin(t * 2.3 + 1.0));
                return Math.Max(0.08, Math.Min(1, 0.15 + 0.85 * syllable * (0.6 + 0.4 * Math.Sin(t * 0.9))));
            }
            for (int i = times.Count - 1; i >= 0; i--)
            {
                if (times[i] > t) continue;
                double after = t - times[i];
                if (i + 1 < times.Count && times[i + 1] - times[i] < 3 * step) return levels[i] + (levels[i + 1] - levels[i]) * after / (times[i + 1] - times[i]);
                return after < 0.2 ? levels[i] * (1 - after / 0.2) : 0;  // the newest value fades if nothing follows
            }
            return 0;
        }
    }

    // The round status light of one session. While the session speaks it becomes five bars
    // that follow the voice.
    class Orb : FrameworkElement
    {
        public const double Size = 36;
        static readonly double[] Weights = { 0.5, 0.8, 1.0, 0.8, 0.5 };
        public string State = "idle";
        public bool Speaking;
        public Wave Wave;

        public Orb() { Width = Height = Size; IsHitTestVisible = false; }

        protected override void OnRender(DrawingContext dc)
        {
            double t = Ui.Now;
            var c = new Point(Size / 2, Size / 2);
            Color tint = Ui.Tint(State);
            if (Speaking)
            {
                double level = Wave.At(t - Wave.Lag);
                dc.DrawEllipse(Ui.Alpha(tint, 0.10 + 0.22 * level), null, c, 13.5 + 4 * level, 13.5 + 4 * level);
                dc.DrawEllipse(Ui.Alpha(tint, 0.30), Ui.Line(tint, 0.95, 1.5), c, 13, 13);
                for (int i = 0; i < 5; i++)
                {
                    double h = 3 + 17 * Weights[i] * Wave.At(t - Wave.Lag - Math.Abs(i - 2) * 0.07);
                    dc.DrawRoundedRectangle(Brushes.White, null, new Rect(c.X + (i - 2) * 4.4 - 1.3, c.Y - h / 2, 2.6, h), 1.3, 1.3);
                }
                return;
            }
            switch (State)
            {
                case "working":
                {
                    dc.DrawEllipse(Ui.Alpha(tint, 0.14), Ui.Line(tint, 0.28, 2), c, 12, 12);
                    double a = t * 4.2, b = a + 1.9;
                    var arc = new StreamGeometry();
                    using (StreamGeometryContext g = arc.Open())
                    {
                        g.BeginFigure(new Point(c.X + 12 * Math.Cos(a), c.Y + 12 * Math.Sin(a)), false, false);
                        g.ArcTo(new Point(c.X + 12 * Math.Cos(b), c.Y + 12 * Math.Sin(b)), new Size(12, 12), 0, false, SweepDirection.Clockwise, true, false);
                    }
                    dc.DrawGeometry(null, Ui.Line(tint, 1, 2.2), arc);
                    dc.DrawEllipse(Ui.Alpha(tint, 0.95), null, c, 3, 3);
                    break;
                }
                case "needs_you":
                {
                    double pulse = 0.5 + 0.5 * Math.Sin(t * 4.5);
                    dc.DrawEllipse(Ui.Alpha(tint, 0.12 * pulse), null, c, 13 + 4 * pulse, 13 + 4 * pulse);
                    dc.DrawEllipse(Ui.Alpha(tint, 0.38 + 0.30 * pulse), Ui.Line(tint, 1, 1.5), c, 13, 13);
                    dc.DrawLine(Ui.Line(Colors.White, 1, 2.6), new Point(c.X, c.Y - 6.5), new Point(c.X, c.Y + 1.5));
                    dc.DrawEllipse(Brushes.White, null, new Point(c.X, c.Y + 6.3), 1.6, 1.6);
                    break;
                }
                case "done":
                {
                    dc.DrawEllipse(Ui.Alpha(tint, 0.26), Ui.Line(tint, 0.95, 1.5), c, 13, 13);
                    Pen pen = Ui.Line(Colors.White, 0.95, 2.3);
                    dc.DrawLine(pen, new Point(c.X - 5.6, c.Y + 0.4), new Point(c.X - 1.8, c.Y + 4.4));
                    dc.DrawLine(pen, new Point(c.X - 1.8, c.Y + 4.4), new Point(c.X + 5.8, c.Y - 4.2));
                    break;
                }
                case "failed":
                {
                    dc.DrawEllipse(Ui.Alpha(tint, 0.30), Ui.Line(tint, 0.95, 1.5), c, 13, 13);
                    Pen pen = Ui.Line(Colors.White, 0.95, 2.3);
                    dc.DrawLine(pen, new Point(c.X - 4.6, c.Y - 4.6), new Point(c.X + 4.6, c.Y + 4.6));
                    dc.DrawLine(pen, new Point(c.X + 4.6, c.Y - 4.6), new Point(c.X - 4.6, c.Y + 4.6));
                    break;
                }
                default:
                    dc.DrawEllipse(Ui.Alpha(tint, 0.08), Ui.Line(tint, 0.65, 1.5), c, 12, 12);
                    dc.DrawEllipse(Ui.Alpha(tint, 0.65), null, c, 2.5, 2.5);
                    break;
            }
        }
    }

    // The last few seconds of the voice as bars flowing behind the text, newest next to the orb.
    class WaveStrip : FrameworkElement
    {
        public Wave Wave;
        public bool NewestRight;
        public Color Tint = Colors.White;

        public WaveStrip() { IsHitTestVisible = false; }

        protected override void OnRender(DrawingContext dc)
        {
            double w = ActualWidth, h = ActualHeight, t = Ui.Now;
            int count = (int)(w / 6);
            if (count < 2 || h < 12) return;
            for (int k = 0; k < count; k++)
            {
                double level = Wave.At(t - Wave.Lag - k * 0.055);
                if (level <= 0.01) continue;
                double tall = 2 + level * (h - 14), x = NewestRight ? w - 5 - k * 6 : 2 + k * 6;
                dc.DrawRoundedRectangle(Ui.Alpha(Tint, 0.34 * (1 - k / (double)count)), null, new Rect(x, (h - tall) / 2, 3, tall), 1.5, 1.5);
            }
        }
    }

    // One see-through piece of the overlay. Windows blurs what is behind a whole window and rounds
    // its corners, and cannot do that for a free shape, so every piece of glass is its own window
    // exactly as big as what it shows. Clicks pass through and it never takes focus.
    class Glass : Window
    {
        const int GWL_EXSTYLE = -20;
        const int WS_EX_TRANSPARENT = 0x20, WS_EX_TOOLWINDOW = 0x80, WS_EX_NOACTIVATE = 0x08000000;
        const uint SWP_NOSIZE = 1, SWP_NOMOVE = 2, SWP_NOACTIVATE = 0x10;
        const int WCA_ACCENT_POLICY = 19, DWMWA_WINDOW_CORNER_PREFERENCE = 33;
        static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);

        [DllImport("user32.dll")] static extern int GetWindowLong(IntPtr hwnd, int index);
        [DllImport("user32.dll")] static extern int SetWindowLong(IntPtr hwnd, int index, int value);
        [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
        [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr hwnd, out WindowRect rect);
        [StructLayout(LayoutKind.Sequential)] struct WindowRect { public int Left, Top, Right, Bottom; }
        [StructLayout(LayoutKind.Sequential)] struct AccentPolicy { public int State, Flags, Color, Animation; }
        [StructLayout(LayoutKind.Sequential)] struct CompositionData { public int Attribute; public IntPtr Data; public int Size; }
        [DllImport("user32.dll")] static extern int SetWindowCompositionAttribute(IntPtr hwnd, ref CompositionData data);
        [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);

        public readonly Border Panel = new Border();
        public readonly IntPtr Handle;

        public Glass()
        {
            WindowStyle = WindowStyle.None;
            AllowsTransparency = true;
            Background = Brushes.Transparent;
            Topmost = true;
            ShowInTaskbar = false;
            ShowActivated = false;
            Focusable = false;
            IsHitTestVisible = false;
            ResizeMode = ResizeMode.NoResize;
            SizeToContent = SizeToContent.WidthAndHeight;
            WindowStartupLocation = WindowStartupLocation.Manual;
            Left = -10000;  // off screen until it is placed
            Top = -10000;
            FontFamily = new FontFamily("Segoe UI");
            FontSize = 13;
            Foreground = Brushes.White;
            Panel.BorderThickness = new Thickness(1);
            Panel.BorderBrush = Ui.GlassEdge;
            Content = Panel;
            Handle = new WindowInteropHelper(this).EnsureHandle();
            // Click-through, no taskbar or Alt+Tab entry, never takes focus from the app in front.
            SetWindowLong(Handle, GWL_EXSTYLE, GetWindowLong(Handle, GWL_EXSTYLE) | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE);
        }

        // kind: blur (Windows blurs what is behind), acrylic (a heavier blur), none (plain dark
        // glass), solid (nothing shows through; for taking pictures of it).
        public void Look(string kind)
        {
            int state = kind == "blur" ? 3 : kind == "acrylic" ? 4 : 0;
            try
            {
                var policy = new AccentPolicy { State = state, Color = 0x01000000 };
                int size = Marshal.SizeOf(policy);
                IntPtr memory = Marshal.AllocHGlobal(size);
                Marshal.StructureToPtr(policy, memory, false);
                var data = new CompositionData { Attribute = WCA_ACCENT_POLICY, Data = memory, Size = size };
                SetWindowCompositionAttribute(Handle, ref data);
                Marshal.FreeHGlobal(memory);
            }
            catch (Exception) { if (state != 0) kind = "none"; }  // a Windows without it
            int corners = kind == "solid" ? 1 : 2;  // 2 = rounded by Windows 11; older versions refuse and stay square
            bool rounded = false;
            try { rounded = DwmSetWindowAttribute(Handle, DWMWA_WINDOW_CORNER_PREFERENCE, ref corners, 4) == 0 && corners == 2; }
            catch (Exception) { }
            Panel.CornerRadius = new CornerRadius(rounded ? 8 : 0);
            Panel.Background = Ui.GlassFill(kind);
        }

        public void CatchMouse(bool on)
        {
            IsHitTestVisible = on;
            int style = GetWindowLong(Handle, GWL_EXSTYLE);
            SetWindowLong(Handle, GWL_EXSTYLE, on ? style & ~WS_EX_TRANSPARENT : style | WS_EX_TRANSPARENT);
        }

        public void Raise() { if (IsVisible) SetWindowPos(Handle, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE); }

        // Left, top, width, height in screen pixels, as Windows has it (WPF's own numbers run ahead
        // of the window while it is being resized).
        public int[] Area()
        {
            WindowRect r;
            GetWindowRect(Handle, out r);
            return new[] { r.Left, r.Top, r.Right - r.Left, r.Bottom - r.Top };
        }
    }

    // One session in the bar: just its status light while the bar is closed, and next to it the
    // session's name, a short title and what it is doing or saying when the bar is open.
    class Row
    {
        public const double Closed = 44, Open = 372;
        public readonly Grid Root = new Grid();
        public readonly Orb Orb = new Orb();
        public readonly WaveStrip Strip = new WaveStrip();
        public readonly Wave Wave;
        readonly Border glow = new Border { CornerRadius = new CornerRadius(6), Background = Ui.Paint("#16FFFFFF") };
        readonly Grid row2 = new Grid();
        readonly StackPanel text = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
        readonly TextBlock line1 = new TextBlock(), line2 = new TextBlock(), meta = new TextBlock();
        public bool Speaking;
        public string Name = "", Title = "", State = "idle", FlashText;
        public double FlashUntil;
        string rowText = "", metaText = "";
        bool open;

        public Row(bool right, Wave wave)
        {
            Wave = Orb.Wave = Strip.Wave = wave;
            Strip.NewestRight = right;
            var textColumn = new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) };
            var orbColumn = new ColumnDefinition { Width = new GridLength(Closed) };
            Root.ColumnDefinitions.Add(right ? textColumn : orbColumn);
            Root.ColumnDefinitions.Add(right ? orbColumn : textColumn);
            int textAt = right ? 0 : 1;
            Grid.SetColumnSpan(glow, 2);
            Grid.SetColumn(Strip, textAt);
            Grid.SetColumn(text, textAt);
            Grid.SetColumn(Orb, 1 - textAt);
            Root.MinHeight = Closed;
            Strip.Margin = right ? new Thickness(8, 0, 0, 0) : new Thickness(0, 0, 8, 0);
            text.Margin = right ? new Thickness(12, 5, 4, 6) : new Thickness(4, 5, 12, 6);
            line1.TextTrimming = line2.TextTrimming = TextTrimming.CharacterEllipsis;
            line2.FontSize = meta.FontSize = 12;
            line2.MaxHeight = 50;  // three lines of a spoken sentence
            meta.Foreground = Ui.Faint;
            meta.FontFamily = Ui.Symbols;
            meta.Margin = new Thickness(8, 0, 0, 0);
            row2.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            row2.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            Grid.SetColumn(meta, 1);
            row2.Children.Add(line2);
            row2.Children.Add(meta);
            text.Children.Add(line1);
            text.Children.Add(row2);
            Root.Children.Add(glow);
            Root.Children.Add(Strip);
            Root.Children.Add(text);
            Root.Children.Add(Orb);
            SetOpen(false);
        }

        public void Update(Dictionary<string, object> s)
        {
            bool was = Speaking;
            Name = Overlay.Str(s, "name");
            Title = Overlay.Str(s, "title");
            State = Orb.State = Overlay.Str(s, "state", "idle");
            Speaking = Orb.Speaking = s.ContainsKey("speaking") && Convert.ToBoolean(s["speaking"]);
            Wave.Synthetic = s.ContainsKey("synth") && Convert.ToBoolean(s["synth"]);
            if (Speaking && !was) Wave.Since = Ui.Now;
            if (!Speaking && was) Wave.Clear();
            Strip.Tint = Ui.Tint(State);
            Overlay.Heading(line1, Name, Title);
            rowText = Overlay.Str(s, "text");
            metaText = Overlay.Str(s, "meta");
            Refresh();
            Orb.InvalidateVisual();
        }

        public bool Saying { get { return FlashText != null && (Speaking || Ui.Now < FlashUntil); } }

        public void SetOpen(bool value)
        {
            open = value;
            Root.Width = open ? Open : Closed;
            text.Visibility = open ? Visibility.Visible : Visibility.Collapsed;
            Refresh();
        }

        // The second line is the sentence being spoken (or just shown) while there is one,
        // otherwise what the session is doing.
        public void Refresh()
        {
            bool saying = Saying;
            line2.Text = saying ? FlashText : rowText;
            line2.TextWrapping = saying ? TextWrapping.Wrap : TextWrapping.NoWrap;
            line2.Foreground = saying ? Brushes.White : Ui.Dim;
            meta.Text = metaText;
            meta.Visibility = saying || metaText.Length == 0 ? Visibility.Collapsed : Visibility.Visible;
            row2.Visibility = line2.Text.Length == 0 && meta.Visibility != Visibility.Visible ? Visibility.Collapsed : Visibility.Visible;
            Strip.Visibility = open && Speaking ? Visibility.Visible : Visibility.Collapsed;
            glow.Visibility = open && saying ? Visibility.Visible : Visibility.Collapsed;
        }
    }

    public class Overlay
    {
        const int WM_HOTKEY = 0x0312;
        const uint MOD_ALT = 1, MOD_CONTROL = 2, MOD_SHIFT = 4, MOD_WIN = 8, MOD_NOREPEAT = 0x4000;
        const double Wide = Row.Open - 24, BubbleWidth = 340, Gap = 8;

        [DllImport("user32.dll")] static extern bool RegisterHotKey(IntPtr hwnd, int id, uint modifiers, uint vk);
        [DllImport("user32.dll")] static extern bool UnregisterHotKey(IntPtr hwnd, int id);
        [DllImport("user32.dll")] static extern short GetAsyncKeyState(int key);
        [DllImport("user32.dll")] static extern bool GetCursorPos(out CursorPoint point);
        [StructLayout(LayoutKind.Sequential)] struct CursorPoint { public int X; public int Y; }

        readonly JavaScriptSerializer json = new JavaScriptSerializer();
        readonly TextWriter output;
        readonly Glass rail = new Glass(), bubble = new Glass();
        readonly StackPanel stack = new StackPanel { Margin = new Thickness(3) };
        readonly StackPanel rowsPanel = new StackPanel();
        readonly StackPanel requestBox = new StackPanel(), bannerBox = new StackPanel(), historyBox = new StackPanel();
        readonly TextBlock requestTitle = new TextBlock(), requestDetail = new TextBlock(), requestKeys = new TextBlock();
        readonly TextBlock bannerTitle = new TextBlock(), bannerHint = new TextBlock();
        readonly TextBlock emptyLine = new TextBlock { Text = "no Claude sessions", Foreground = Ui.Faint, Margin = new Thickness(12, 10, 12, 10), Width = Wide };
        readonly TextBlock bubbleLine1 = new TextBlock(), bubbleLine2 = new TextBlock();
        readonly WaveStrip bubbleStrip = new WaveStrip();
        readonly Dictionary<string, Row> rows = new Dictionary<string, Row>();
        readonly Dictionary<string, Wave> waves = new Dictionary<string, Wave>();
        readonly Dictionary<string, KeyValuePair<string, double>> flashes = new Dictionary<string, KeyValuePair<string, double>>();
        readonly DispatcherTimer frameTimer = new DispatcherTimer(DispatcherPriority.Render);
        readonly DispatcherTimer hoverTimer = new DispatcherTimer();
        readonly DispatcherTimer moveTimer = new DispatcherTimer();
        readonly DispatcherTimer bannerTimer = new DispatcherTimer();
        readonly DispatcherTimer holdTimer = new DispatcherTimer();
        readonly DispatcherTimer topTimer = new DispatcherTimer();
        readonly Dictionary<int, string> hotkeys = new Dictionary<int, string>();        // registered id -> name
        readonly Dictionary<int, uint> hotkeyKeys = new Dictionary<int, uint>();         // registered id -> key
        readonly Dictionary<string, string> wantedKeys = new Dictionary<string, string>(); // name -> "Ctrl+Alt+L"
        readonly HashSet<string> liveKeys = new HashSet<string>();  // names claimed only while they can act
        readonly HashSet<string> complained = new HashSet<string>();  // hotkey problems already reported
        uint heldKey;
        readonly IntPtr hwnd;

        object[] sessions = new object[0];
        object[] history = new object[0];
        int monitor, insideTicks, outsideTicks;  // monitor: 0 = primary, 1.. = the others in Windows' order
        bool moving, hover, peek, peekForced, opaque, hasRequest, hasBanner;
        string mode = "dots", corner = "top-right", glass = "blur", bubbleShows = "";
        double offsetX = 12, offsetY = 96, idleOpacity = 0.9, listOpacity = 1.0, lastFade = -1;
        Row talker;  // the session the speech bubble belongs to

        Overlay(TextWriter output)
        {
            this.output = output;
            hwnd = rail.Handle;

            requestTitle.TextWrapping = requestKeys.TextWrapping = requestDetail.TextWrapping = TextWrapping.Wrap;
            requestTitle.MaxHeight = 54;
            requestTitle.TextTrimming = requestDetail.TextTrimming = TextTrimming.CharacterEllipsis;
            requestDetail.FontFamily = new FontFamily("Consolas");
            requestDetail.Foreground = Ui.Dim;
            requestDetail.MaxHeight = 70;  // about four lines; the terminal has the full command
            requestDetail.Margin = new Thickness(0, 4, 0, 4);
            requestKeys.Foreground = Ui.AmberEdge;
            Section(requestBox, true, requestTitle, requestDetail, requestKeys);
            bannerTitle.TextWrapping = bannerHint.TextWrapping = TextWrapping.Wrap;
            bannerHint.Foreground = Ui.Faint;
            bannerHint.Margin = new Thickness(0, 2, 0, 0);
            Section(bannerBox, true, bannerTitle, bannerHint);
            Section(historyBox, false);

            stack.Children.Add(bannerBox);
            stack.Children.Add(requestBox);
            stack.Children.Add(emptyLine);
            stack.Children.Add(rowsPanel);
            stack.Children.Add(historyBox);
            rail.Panel.Child = stack;

            // The speech bubble: who is talking, the sentence, and the voice flowing behind it.
            bubbleLine1.TextTrimming = bubbleLine2.TextTrimming = TextTrimming.CharacterEllipsis;
            bubbleLine2.TextWrapping = TextWrapping.Wrap;
            bubbleLine2.MaxHeight = 68;  // four lines
            bubbleLine2.Margin = new Thickness(0, 2, 0, 0);
            var words = new StackPanel { Margin = new Thickness(14, 8, 14, 10) };
            words.Children.Add(bubbleLine1);
            words.Children.Add(bubbleLine2);
            var layers = new Grid { Width = BubbleWidth };
            layers.Children.Add(bubbleStrip);
            layers.Children.Add(words);
            bubble.Panel.Child = layers;

            rail.SizeChanged += delegate { Place(); };
            bubble.SizeChanged += delegate { PlaceBubble(); };
            // About 30 pictures a second, and only while something moves.
            frameTimer.Interval = TimeSpan.FromMilliseconds(33);
            frameTimer.Tick += delegate { Frame(); };
            bannerTimer.Tick += delegate { bannerTimer.Stop(); hasBanner = false; Render(); };
            // Clicks pass through, so "the mouse is on me" is found by watching where the cursor is.
            hoverTimer.Interval = TimeSpan.FromMilliseconds(100);
            hoverTimer.Tick += delegate { WatchCursor(); };
            moveTimer.Tick += delegate { EndMove(); };
            rail.MouseLeftButtonDown += delegate(object sender, MouseButtonEventArgs e) {
                if (!moving) return;
                rail.DragMove();  // returns when the button is released
                ReportMoved();
                moveTimer.Stop(); moveTimer.Interval = TimeSpan.FromSeconds(4); moveTimer.Start();
            };
            // Hold-to-talk: a hotkey only reports the press, so watch the key until it comes back up.
            holdTimer.Interval = TimeSpan.FromMilliseconds(30);
            holdTimer.Tick += delegate {
                if ((GetAsyncKeyState((int)heldKey) & 0x8000) != 0) return;
                holdTimer.Stop();
                Send("hotkey", "name", "talk_end");
            };
            // Other always-on-top windows (and some games) push us down; climb back regularly.
            topTimer.Interval = TimeSpan.FromSeconds(2);
            topTimer.Tick += delegate { rail.Raise(); bubble.Raise(); };

            HwndSource.FromHwnd(hwnd).AddHook(WndProc);
            SetGlass();
            topTimer.Start();
            hoverTimer.Start();
        }

        [STAThread]
        public static void Main()
        {
            try { Run(); }
            catch (Exception e)
            {
                Console.Out.WriteLine("{\"type\":\"error\",\"message\":\"" + e.Message.Replace('"', '\'').Replace('\\', '/') + "\"}");
                Environment.Exit(1);
            }
        }

        public static void Run()
        {
            var output = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false));
            output.AutoFlush = true;
            var app = new Application();
            app.ShutdownMode = ShutdownMode.OnExplicitShutdown;
            var overlay = new Overlay(output);
            app.DispatcherUnhandledException += delegate(object sender, DispatcherUnhandledExceptionEventArgs e) {
                overlay.Error(e.Exception.Message);
                e.Handled = true;
            };
            var reader = new Thread(overlay.ReadLoop);
            reader.IsBackground = true;
            reader.Start();
            overlay.Send("ready", null, null);
            app.Run();
        }

        // --- input from the hub -------------------------------------------------------------------

        void ReadLoop()
        {
            var reader = new StreamReader(Console.OpenStandardInput(), new UTF8Encoding(false));
            string line;
            while ((line = reader.ReadLine()) != null)
            {
                if (line.Trim().Length == 0) continue;
                string captured = line;
                rail.Dispatcher.BeginInvoke(new Action(delegate { Handle(captured); }));
            }
            // The hub is gone (pipe closed): nothing left to show.
            rail.Dispatcher.BeginInvoke(new Action(delegate { Application.Current.Shutdown(); }));
        }

        void Handle(string line)
        {
            Dictionary<string, object> msg;
            try { msg = (Dictionary<string, object>)json.DeserializeObject(line); }
            catch (Exception e) { Error("bad message: " + e.Message); return; }

            switch (Str(msg, "type"))
            {
                case "config":
                    string side = corner;
                    corner = Str(msg, "corner", corner);
                    offsetX = Num(msg, "offset_x", offsetX);
                    offsetY = Num(msg, "offset_y", offsetY);
                    idleOpacity = Num(msg, "opacity", idleOpacity);
                    listOpacity = Num(msg, "list_opacity", listOpacity);
                    monitor = (int)Num(msg, "monitor", monitor);
                    opaque = msg.ContainsKey("opaque") && Convert.ToBoolean(msg["opaque"]);
                    glass = Str(msg, "glass", glass);
                    SetGlass();
                    if (side.EndsWith("right") != corner.EndsWith("right")) ForgetRows();  // the lights change sides
                    if (msg.ContainsKey("hotkeys"))
                    {
                        wantedKeys.Clear();
                        foreach (KeyValuePair<string, object> entry in (Dictionary<string, object>)msg["hotkeys"])
                            wantedKeys[entry.Key] = Convert.ToString(entry.Value);
                        RegisterHotkeys();
                    }
                    if (msg.ContainsKey("mode")) mode = Str(msg, "mode", mode);
                    Render();
                    Place();
                    break;
                case "state":
                    sessions = msg.ContainsKey("sessions") ? (object[])msg["sessions"] : new object[0];
                    history = msg.ContainsKey("history") ? (object[])msg["history"] : new object[0];
                    Render();
                    break;
                case "flash":
                    Flash(msg);
                    break;
                case "wave":
                    AddWave(msg);
                    break;
                case "request":
                    ShowRequest(msg);
                    break;
                case "banner":
                    ShowBanner(msg);
                    break;
                case "keys":
                    liveKeys.Clear();
                    if (msg.ContainsKey("live")) foreach (object name in (object[])msg["live"]) liveKeys.Add(Convert.ToString(name));
                    RegisterHotkeys();
                    break;
                case "mode":
                    SetMode(Str(msg, "mode", "toggle"));
                    break;
                case "move":
                    if (msg.ContainsKey("on") && !Convert.ToBoolean(msg["on"])) EndMove(); else BeginMove();
                    break;
                case "peek":  // open the bar and the history without a mouse (for checking how it looks)
                    peekForced = hover = msg.ContainsKey("on") && Convert.ToBoolean(msg["on"]);
                    peek = peekForced && mode == "list";
                    Render();
                    break;
                case "bounds":
                    ReportBounds();
                    break;
                case "quit":
                    Application.Current.Shutdown();
                    break;
            }
        }

        // --- drawing --------------------------------------------------------------------------------

        void SetGlass()
        {
            string kind = opaque ? "solid" : glass;
            rail.Look(kind);
            bubble.Look(kind);
        }

        // A block of text inside the open bar, with a hairline under or over it.
        static void Section(StackPanel box, bool lineBelow, params UIElement[] children)
        {
            var body = new StackPanel { Margin = new Thickness(12, 8, 12, 9), Width = Wide };
            foreach (UIElement child in children) body.Children.Add(child);
            var line = new Border { Height = 1, Background = Ui.Paint("#30FFFFFF"), Margin = new Thickness(8, 0, 8, 0) };
            if (!lineBelow) box.Children.Add(line);
            box.Children.Add(body);
            if (lineBelow) box.Children.Add(line);
        }

        // "name   title", the name in bold.
        internal static void Heading(TextBlock line, string name, string title)
        {
            line.Inlines.Clear();
            line.Inlines.Add(new Run(name) { FontWeight = FontWeights.SemiBold });
            if (title.Length > 0) line.Inlines.Add(new Run("   " + title) { Foreground = Ui.Dim });
        }

        // The bar is open (names, titles, what each session is doing) in list mode, under the
        // mouse, and while it has something to ask or show. Otherwise it is only the lights.
        bool IsOpen() { return mode == "list" || hover || moving || hasRequest || hasBanner; }

        void Render()
        {
            bool isList = mode == "list", open = IsOpen();
            SyncRows();
            foreach (Row row in rows.Values) row.SetOpen(open);
            requestBox.Visibility = hasRequest ? Visibility.Visible : Visibility.Collapsed;
            bannerBox.Visibility = hasBanner ? Visibility.Visible : Visibility.Collapsed;
            emptyLine.Visibility = open && sessions.Length == 0 && !hasRequest && !hasBanner ? Visibility.Visible : Visibility.Collapsed;
            bool showHistory = isList && peek && history.Length > 0;
            historyBox.Visibility = showHistory ? Visibility.Visible : Visibility.Collapsed;
            if (showHistory) BuildHistory();
            bool show = isList || hasRequest || hasBanner || moving || sessions.Length > 0;
            if (show && !rail.IsVisible) rail.Show();
            else if (!show && rail.IsVisible) rail.Hide();
            UpdateBubble();
            Fade();
            if (!frameTimer.IsEnabled) frameTimer.Start();
        }

        // Keeps one row per session, in the hub's order, without rebuilding the ones that stay.
        void SyncRows()
        {
            bool right = corner.EndsWith("right");
            var wanted = new List<Row>();
            var names = new HashSet<string>();
            foreach (object o in sessions)
            {
                var s = (Dictionary<string, object>)o;
                string name = Str(s, "name");
                Row row;
                if (!rows.TryGetValue(name, out row))
                {
                    row = rows[name] = new Row(right, WaveOf(name));
                    KeyValuePair<string, double> flash;
                    if (flashes.TryGetValue(name, out flash)) { row.FlashText = flash.Key; row.FlashUntil = flash.Value; }
                }
                row.Update(s);
                wanted.Add(row);
                names.Add(name);
            }
            foreach (string gone in new List<string>(rows.Keys))
                if (!names.Contains(gone)) { rows.Remove(gone); waves.Remove(gone); flashes.Remove(gone); }
            bool same = rowsPanel.Children.Count == wanted.Count;
            for (int i = 0; same && i < wanted.Count; i++) same = rowsPanel.Children[i] == wanted[i].Root;
            if (same) return;
            rowsPanel.Children.Clear();
            foreach (Row row in wanted) rowsPanel.Children.Add(row.Root);
        }

        void ForgetRows()
        {
            rows.Clear();
            rowsPanel.Children.Clear();
            talker = null;
        }

        Wave WaveOf(string name)
        {
            Wave wave;
            if (!waves.TryGetValue(name, out wave)) wave = waves[name] = new Wave();
            return wave;
        }

        // While the bar is closed, the session that is talking (or was just shown) gets a bubble
        // next to its light with the sentence and the voice.
        void UpdateBubble()
        {
            Row found = null;
            if (!IsOpen() && rail.IsVisible)
                foreach (Row row in rows.Values)
                    if (row.Saying && (found == null || row.Speaking || (!found.Speaking && row.FlashUntil > found.FlashUntil))) found = row;
            talker = found;
            if (found == null)
            {
                bubbleShows = "";
                if (bubble.IsVisible) bubble.Hide();
                return;
            }
            string shows = found.Name + "\n" + found.Title + "\n" + found.FlashText + "\n" + found.State;
            if (shows != bubbleShows)
            {
                bubbleShows = shows;
                Heading(bubbleLine1, found.Name, found.Title);
                bubbleLine2.Text = found.FlashText;
                bubbleStrip.Wave = found.Wave;
                bubbleStrip.Tint = Ui.Tint(found.State);
                bubbleStrip.NewestRight = corner.EndsWith("right");
            }
            if (!bubble.IsVisible) bubble.Show();
            PlaceBubble();
        }

        // One step of what moves: spinners, pulses and the voice wave.
        void Frame()
        {
            double now = Ui.Now;
            bool again = false, expired = false;
            foreach (Row row in rows.Values)
            {
                if (row.FlashText != null && !row.Speaking && now >= row.FlashUntil) { row.FlashText = null; row.Refresh(); expired = true; }
                if (row.Speaking || row.State == "working" || row.State == "needs_you")
                {
                    row.Orb.InvalidateVisual();
                    if (row.Speaking) row.Strip.InvalidateVisual();
                    again = true;
                }
                if (row.FlashText != null) again = true;  // so its end is noticed
            }
            if (expired) { UpdateBubble(); Fade(); }
            if (bubble.IsVisible) bubbleStrip.InvalidateVisual();
            if (!again) frameTimer.Stop();
        }

        // What sessions said lately, shown under the list while the cursor rests on it.
        void BuildHistory()
        {
            var body = (StackPanel)historyBox.Children[1];
            body.Children.Clear();
            foreach (object o in history)
            {
                var h = (Dictionary<string, object>)o;
                var line = new TextBlock { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 2, 0, 2), FontSize = 12, MaxHeight = 34, TextTrimming = TextTrimming.CharacterEllipsis };
                line.Inlines.Add(new Run(Str(h, "ago") + "  ") { Foreground = Ui.Faint });
                line.Inlines.Add(new Run(Str(h, "name") + "  ") { FontWeight = FontWeights.SemiBold });
                line.Inlines.Add(new Run(Str(h, "text")) { Foreground = Ui.Dim });
                body.Children.Add(line);
            }
        }

        // The bar opens when the mouse rests on it and closes shortly after it leaves.
        // In list mode, resting a little longer also shows the history.
        void WatchCursor()
        {
            CursorPoint cursor;
            if (peekForced || moving || !rail.IsVisible || !GetCursorPos(out cursor)) return;
            int[] area = rail.Area();
            bool inside = cursor.X >= area[0] - 6 && cursor.X <= area[0] + area[2] + 6 && cursor.Y >= area[1] - 6 && cursor.Y <= area[1] + area[3] + 6;
            if (inside) { insideTicks++; outsideTicks = 0; } else { outsideTicks++; insideTicks = 0; }
            bool wantHover = inside ? insideTicks >= 2 || hover : hover && outsideTicks < 5;
            bool wantPeek = mode == "list" && (inside ? insideTicks >= 6 || peek : peek && outsideTicks < 5);
            if (wantHover == hover && wantPeek == peek) return;
            hover = wantHover;
            peek = wantPeek;
            Render();
        }

        // "Move" makes the bar catch the mouse for a few seconds so it can be dragged.
        void BeginMove()
        {
            moving = true;
            rail.CatchMouse(true);
            rail.Panel.BorderBrush = Ui.AmberEdge;
            bannerTimer.Stop();
            hasBanner = true;
            bannerTitle.Inlines.Clear();
            bannerTitle.Inlines.Add(new Run("drag me to where you want me") { FontWeight = FontWeights.SemiBold });
            bannerHint.Text = "any monitor \u00B7 I stay there once you let go for a few seconds";
            bannerHint.Visibility = Visibility.Visible;
            moveTimer.Stop(); moveTimer.Interval = TimeSpan.FromSeconds(15); moveTimer.Start();
            Render();
        }

        void EndMove()
        {
            moveTimer.Stop();
            moving = false;
            hasBanner = false;
            rail.CatchMouse(false);
            rail.Panel.BorderBrush = Ui.GlassEdge;
            Render();
            Place();
        }

        // Where it was dropped, as "which monitor, which corner, how far from it", so it keeps its
        // place when its size changes.
        void ReportMoved()
        {
            int[] area = rail.Area();
            var centre = new System.Drawing.Point(area[0] + area[2] / 2, area[1] + area[3] / 2);
            System.Windows.Forms.Screen screen = System.Windows.Forms.Screen.FromPoint(centre);
            monitor = 0;
            int n = 0;
            foreach (System.Windows.Forms.Screen other in System.Windows.Forms.Screen.AllScreens)
            {
                if (other.Primary) continue;
                n++;
                if (other.DeviceName == screen.DeviceName) monitor = n;
            }
            Rect work = WorkArea();
            bool wasRight = corner.EndsWith("right");
            double left = rail.Left, top = rail.Top, wide = rail.ActualWidth, tall = rail.ActualHeight;
            bool right = left + wide / 2 > work.Left + work.Width / 2, bottom = top + tall / 2 > work.Top + work.Height / 2;
            corner = (bottom ? "bottom" : "top") + "-" + (right ? "right" : "left");
            offsetX = Math.Max(0, right ? work.Right - (left + wide) : left - work.Left);
            offsetY = Math.Max(0, bottom ? work.Bottom - (top + tall) : top - work.Top);
            if (right != wasRight) { ForgetRows(); Render(); }  // the lights change sides
            Write(new Dictionary<string, object> {
                { "type", "moved" }, { "monitor", monitor }, { "corner", corner },
                { "offset_x", Math.Round(offsetX) }, { "offset_y", Math.Round(offsetY) },
            });
        }

        // The chosen monitor's usable area, in the units WPF positions windows in.
        Rect WorkArea()
        {
            System.Windows.Forms.Screen screen = System.Windows.Forms.Screen.PrimaryScreen;
            int n = 0;
            foreach (System.Windows.Forms.Screen other in System.Windows.Forms.Screen.AllScreens)
            {
                if (other.Primary) continue;
                n++;
                if (n == monitor) screen = other;
            }
            System.Drawing.Rectangle area = screen.WorkingArea;
            Matrix fromDevice = HwndSource.FromHwnd(hwnd).CompositionTarget.TransformFromDevice;
            return new Rect(fromDevice.Transform(new Point(area.Left, area.Top)), fromDevice.Transform(new Point(area.Right, area.Bottom)));
        }

        // A line about one session, shown for a few seconds (and for as long as it is being
        // spoken): in its row when the bar is open, in the bubble when it is closed.
        void Flash(Dictionary<string, object> msg)
        {
            string name = Str(msg, "name"), text = Str(msg, "text");
            double until = Ui.Now + Num(msg, "seconds", 4);
            flashes[name] = new KeyValuePair<string, double>(text, until);
            Row row;
            if (rows.TryGetValue(name, out row)) { row.FlashText = text; row.FlashUntil = until; row.Refresh(); }
            Render();
        }

        void AddWave(Dictionary<string, object> msg)
        {
            if (!msg.ContainsKey("levels")) return;
            var raw = (object[])msg["levels"];
            var levels = new double[raw.Length];
            for (int i = 0; i < raw.Length; i++) levels[i] = Convert.ToDouble(raw[i], CultureInfo.InvariantCulture);
            WaveOf(Str(msg, "name")).Add(Ui.Now + Num(msg, "delay", 0), Math.Max(0.005, Num(msg, "step", 0.04)), levels);
            if (!frameTimer.IsEnabled) frameTimer.Start();
        }

        // A permission prompt or question stays on screen until it is answered: the hotkeys act on it.
        void ShowRequest(Dictionary<string, object> msg)
        {
            hasRequest = msg.ContainsKey("text");
            if (hasRequest)
            {
                requestTitle.Inlines.Clear();
                requestTitle.Inlines.Add(new Run("\u25B2  ") { Foreground = Ui.AmberEdge, FontFamily = Ui.Symbols });
                requestTitle.Inlines.Add(new Run(Str(msg, "name") + "  ") { FontWeight = FontWeights.SemiBold });
                requestTitle.Inlines.Add(new Run(Str(msg, "text")));
                requestDetail.Text = Str(msg, "detail");
                requestDetail.Visibility = requestDetail.Text.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
                requestKeys.Text = Str(msg, "keys");
            }
            Render();
        }

        // Push-to-talk feedback: who is being recorded for, the transcript about to be sent, and so on.
        void ShowBanner(Dictionary<string, object> msg)
        {
            bannerTimer.Stop();
            hasBanner = msg.ContainsKey("text") && msg["text"] != null;
            if (hasBanner)
            {
                bannerTitle.Inlines.Clear();
                bannerTitle.Inlines.Add(new Run("\uD83C\uDFA4  ") { Foreground = Ui.Alpha(Ui.Tint("working"), 1), FontFamily = Ui.Symbols });
                bannerTitle.Inlines.Add(new Run(Str(msg, "text")) { FontWeight = FontWeights.SemiBold });
                bannerHint.Text = Str(msg, "hint");
                bannerHint.Visibility = bannerHint.Text.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
                double seconds = Num(msg, "seconds", 0);
                if (seconds > 0) { bannerTimer.Interval = TimeSpan.FromSeconds(seconds); bannerTimer.Start(); }
            }
            Render();
        }

        void SetMode(string wanted)
        {
            mode = wanted == "toggle" ? (mode == "list" ? "dots" : "list") : (wanted == "list" ? "list" : "dots");
            if (mode != "list") peek = false;
            Render();
            Send("mode", "mode", mode);
        }

        // Solid while something is happening or the mouse is on it, a little fainter at rest.
        void Fade()
        {
            bool busy = hasRequest || hasBanner || moving || hover || peek;
            foreach (Row row in rows.Values) busy = busy || row.Saying;
            double target = opaque || busy ? 1.0 : (mode == "list" ? listOpacity : idleOpacity);
            if (target == lastFade) return;
            lastFade = target;
            stack.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(target, TimeSpan.FromMilliseconds(200)));
        }

        void Place()
        {
            Rect work = WorkArea();
            bool right = corner.EndsWith("right"), bottom = corner.StartsWith("bottom");
            rail.Left = right ? work.Right - rail.ActualWidth - offsetX : work.Left + offsetX;
            rail.Top = bottom ? work.Bottom - rail.ActualHeight - offsetY : work.Top + offsetY;
            PlaceBubble();
        }

        // Beside the bar, level with the light of the session that is talking.
        void PlaceBubble()
        {
            if (talker == null || !bubble.IsVisible || !rail.IsVisible) return;
            double level = rail.ActualHeight / 2;
            try { level = talker.Root.TransformToAncestor(rail).Transform(new Point(0, talker.Root.ActualHeight / 2)).Y; }
            catch (InvalidOperationException) { }  // its row is not on screen yet
            Rect work = WorkArea();
            double top = rail.Top + level - bubble.ActualHeight / 2;
            bubble.Top = Math.Max(work.Top + 4, Math.Min(work.Bottom - bubble.ActualHeight - 4, top));
            bubble.Left = corner.EndsWith("right") ? rail.Left - bubble.ActualWidth - Gap : rail.Left + rail.ActualWidth + Gap;
        }

        // --- hotkeys --------------------------------------------------------------------------------

        // Claims the global hotkeys. Keys that answer something (allow, deny, cancel, option1-4) are
        // claimed only while the hub says they can act, so those combinations stay free for other
        // programs the rest of the time. The others (toggle, talk, repeat, missed) are always claimed.
        void RegisterHotkeys()
        {
            foreach (int id in hotkeys.Keys) UnregisterHotKey(hwnd, id);
            hotkeys.Clear();
            hotkeyKeys.Clear();
            int next = 1;
            foreach (KeyValuePair<string, string> entry in wantedKeys)
            {
                bool answers = entry.Key == "allow" || entry.Key == "deny" || entry.Key == "cancel" || entry.Key.StartsWith("option");
                if (answers && !liveKeys.Contains(entry.Key)) continue;
                string combo = entry.Value;
                if (combo.Trim().Length == 0) continue;  // an empty combo turns that hotkey off
                uint modifiers = MOD_NOREPEAT, vk = 0;
                try
                {
                    foreach (string raw in combo.Split('+'))
                    {
                        string part = raw.Trim();
                        switch (part.ToLowerInvariant())
                        {
                            case "ctrl": case "control": modifiers |= MOD_CONTROL; break;
                            case "alt": modifiers |= MOD_ALT; break;
                            case "shift": modifiers |= MOD_SHIFT; break;
                            case "win": modifiers |= MOD_WIN; break;
                            case "backspace": vk = (uint)KeyInterop.VirtualKeyFromKey(Key.Back); break;
                            case "esc": vk = (uint)KeyInterop.VirtualKeyFromKey(Key.Escape); break;
                            default: vk = (uint)KeyInterop.VirtualKeyFromKey((Key)new KeyConverter().ConvertFromInvariantString(part)); break;
                        }
                    }
                }
                catch (Exception) { vk = 0; }
                if (vk == 0) { if (complained.Add(combo)) Error("hotkey not understood: " + combo); continue; }
                if (RegisterHotKey(hwnd, next, modifiers, vk)) { hotkeys[next] = entry.Key; hotkeyKeys[next] = vk; next++; }
                else if (complained.Add(combo)) Error("hotkey " + combo + " is already taken by another program");
            }
        }

        IntPtr WndProc(IntPtr window, int message, IntPtr wParam, IntPtr lParam, ref bool handled)
        {
            string name;
            if (message == WM_HOTKEY && hotkeys.TryGetValue(wParam.ToInt32(), out name))
            {
                if (name == "toggle") SetMode("toggle");
                if (name == "talk") { heldKey = hotkeyKeys[wParam.ToInt32()]; holdTimer.Start(); }
                Send("hotkey", "name", name);
                handled = true;
            }
            return IntPtr.Zero;
        }

        // --- output to the hub ------------------------------------------------------------------

        // Where the pieces are on screen, so a check can take a picture of exactly those.
        void ReportBounds()
        {
            rail.UpdateLayout();
            bubble.UpdateLayout();
            var reply = new Dictionary<string, object> { { "type", "bounds" }, { "visible", rail.IsVisible } };
            if (rail.IsVisible)
            {
                var pieces = new List<object> { rail.Area() };
                if (bubble.IsVisible) pieces.Add(bubble.Area());
                int[] area = rail.Area();
                reply["x"] = area[0]; reply["y"] = area[1]; reply["w"] = area[2]; reply["h"] = area[3];
                reply["pieces"] = pieces;
                reply["open"] = IsOpen();
                reply["layout"] = new[] { (int)rail.ActualWidth, (int)rail.ActualHeight };
                reply["opacity"] = stack.Opacity;
                reply["monitor"] = monitor;
                reply["catches_mouse"] = moving;
            }
            Write(reply);
        }

        void Send(string type, string key, object value)
        {
            var msg = new Dictionary<string, object> { { "type", type } };
            if (key != null) msg[key] = value;
            Write(msg);
        }

        void Error(string message) { Send("error", "message", message); }

        void Write(Dictionary<string, object> msg)
        {
            lock (output) { output.WriteLine(json.Serialize(msg)); }
        }

        // --- small helpers ------------------------------------------------------------------------

        internal static string Str(Dictionary<string, object> d, string key) { return Str(d, key, ""); }

        internal static string Str(Dictionary<string, object> d, string key, string fallback)
        {
            object v;
            return d.TryGetValue(key, out v) && v != null ? Convert.ToString(v, CultureInfo.InvariantCulture) : fallback;
        }

        static double Num(Dictionary<string, object> d, string key, double fallback)
        {
            object v;
            return d.TryGetValue(key, out v) && v != null ? Convert.ToDouble(v, CultureInfo.InvariantCulture) : fallback;
        }
    }
}
