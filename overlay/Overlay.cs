// The claude-speaks overlay window. It only draws what the hub tells it to and reports hotkeys.
// Protocol: one JSON object per line. In on stdin: config, state, flash, request, mode, bounds, quit.
// Out on stdout: ready, hotkey, mode, bounds, error.
// Compiled by Windows PowerShell 5.1 (Add-Type), so this file must stay within C# 5 and ASCII.
using System;
using System.Collections.Generic;
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
    public class Overlay : Window
    {
        const int GWL_EXSTYLE = -20;
        const int WS_EX_TRANSPARENT = 0x20, WS_EX_TOOLWINDOW = 0x80, WS_EX_NOACTIVATE = 0x08000000;
        const int WM_HOTKEY = 0x0312;
        const uint MOD_ALT = 1, MOD_CONTROL = 2, MOD_SHIFT = 4, MOD_WIN = 8, MOD_NOREPEAT = 0x4000;
        const uint SWP_NOSIZE = 1, SWP_NOMOVE = 2, SWP_NOACTIVATE = 0x10;
        static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);

        [DllImport("user32.dll")] static extern int GetWindowLong(IntPtr hwnd, int index);
        [DllImport("user32.dll")] static extern int SetWindowLong(IntPtr hwnd, int index, int value);
        [DllImport("user32.dll")] static extern bool RegisterHotKey(IntPtr hwnd, int id, uint modifiers, uint vk);
        [DllImport("user32.dll")] static extern bool UnregisterHotKey(IntPtr hwnd, int id);
        [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int cx, int cy, uint flags);

        // state -> { glyph, color }. Shape differs as well as color, so it reads without color vision.
        static readonly Dictionary<string, string[]> Looks = new Dictionary<string, string[]> {
            { "working",   new[] { "●", "#4FC3F7" } },
            { "needs_you", new[] { "▲", "#FFB300" } },
            { "done",      new[] { "✔", "#66BB6A" } },
            { "failed",    new[] { "✖", "#EF5350" } },
            { "idle",      new[] { "○", "#9E9E9E" } },
        };
        const string Speaker = "🔊";
        static readonly FontFamily Symbols = new FontFamily("Segoe UI Symbol");

        readonly JavaScriptSerializer json = new JavaScriptSerializer();
        readonly TextWriter output;
        readonly Border panel = new Border();
        readonly StackPanel dots = new StackPanel { Orientation = Orientation.Horizontal };
        readonly TextBlock flashLine = new TextBlock();
        readonly StackPanel list = new StackPanel();
        readonly StackPanel requestBox = new StackPanel { Margin = new Thickness(0, 0, 0, 4) };
        readonly TextBlock requestTitle = new TextBlock();
        readonly TextBlock requestDetail = new TextBlock();
        readonly TextBlock requestKeys = new TextBlock();
        readonly DispatcherTimer flashTimer = new DispatcherTimer();
        readonly DispatcherTimer topTimer = new DispatcherTimer();
        readonly Dictionary<int, string> hotkeys = new Dictionary<int, string>();
        readonly IntPtr hwnd;

        object[] sessions = new object[0];
        string mode = "dots", corner = "top-right";
        double offsetX = 150, offsetY = 8, idleOpacity = 0.35, listOpacity = 0.85;
        bool flashing, opaque, hasRequest;

        Overlay(TextWriter output)
        {
            this.output = output;
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
            Left = -10000;  // off screen until the first layout places it
            Top = -10000;
            FontFamily = new FontFamily("Segoe UI");
            FontSize = 13;
            Foreground = Brushes.White;

            requestTitle.MaxWidth = requestDetail.MaxWidth = requestKeys.MaxWidth = 620;
            requestTitle.TextTrimming = TextTrimming.CharacterEllipsis;
            requestDetail.FontFamily = new FontFamily("Consolas");
            requestDetail.Foreground = Paint("#DDDDDD");
            requestDetail.TextWrapping = TextWrapping.Wrap;
            requestDetail.TextTrimming = TextTrimming.CharacterEllipsis;
            requestDetail.MaxHeight = 52;  // about three lines; the terminal has the full command
            requestDetail.Margin = new Thickness(0, 2, 0, 2);
            requestKeys.Foreground = Paint("#FFB300");
            requestBox.Children.Add(requestTitle);
            requestBox.Children.Add(requestDetail);
            requestBox.Children.Add(requestKeys);

            var stack = new StackPanel();
            stack.Children.Add(requestBox);
            stack.Children.Add(dots);
            stack.Children.Add(flashLine);
            stack.Children.Add(list);
            panel.Child = stack;
            panel.CornerRadius = new CornerRadius(8);
            panel.Padding = new Thickness(10, 6, 10, 6);
            panel.Background = Paint("#E6161616");
            Content = panel;
            flashLine.MaxWidth = 620;
            flashLine.TextTrimming = TextTrimming.CharacterEllipsis;

            SizeChanged += delegate { Place(); };
            flashTimer.Tick += delegate { flashTimer.Stop(); flashing = false; Render(); };
            // Other always-on-top windows (and some games) push us down; climb back regularly.
            topTimer.Interval = TimeSpan.FromSeconds(2);
            topTimer.Tick += delegate { SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE); };

            hwnd = new WindowInteropHelper(this).EnsureHandle();
            // Click-through, no taskbar or Alt+Tab entry, never takes focus from the app in front.
            SetWindowLong(hwnd, GWL_EXSTYLE, GetWindowLong(hwnd, GWL_EXSTYLE) | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE);
            HwndSource.FromHwnd(hwnd).AddHook(WndProc);
            topTimer.Start();
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
                Dispatcher.BeginInvoke(new Action(delegate { Handle(captured); }));
            }
            // The hub is gone (pipe closed): nothing left to show.
            Dispatcher.BeginInvoke(new Action(delegate { Application.Current.Shutdown(); }));
        }

        void Handle(string line)
        {
            Dictionary<string, object> msg;
            try { msg = (Dictionary<string, object>)json.DeserializeObject(line); }
            catch (Exception e) { Error("bad message: " + e.Message); return; }

            switch (Str(msg, "type"))
            {
                case "config":
                    corner = Str(msg, "corner", corner);
                    offsetX = Num(msg, "offset_x", offsetX);
                    offsetY = Num(msg, "offset_y", offsetY);
                    idleOpacity = Num(msg, "opacity", idleOpacity);
                    listOpacity = Num(msg, "list_opacity", listOpacity);
                    opaque = msg.ContainsKey("opaque") && Convert.ToBoolean(msg["opaque"]);
                    panel.Background = Paint(opaque ? "#FF161616" : "#E6161616");
                    if (msg.ContainsKey("hotkeys")) RegisterHotkeys((Dictionary<string, object>)msg["hotkeys"]);
                    if (msg.ContainsKey("mode")) mode = Str(msg, "mode", mode);
                    Render();
                    Place();
                    break;
                case "state":
                    sessions = msg.ContainsKey("sessions") ? (object[])msg["sessions"] : new object[0];
                    Render();
                    break;
                case "flash":
                    Flash(msg);
                    break;
                case "request":
                    ShowRequest(msg);
                    break;
                case "mode":
                    SetMode(Str(msg, "mode", "toggle"));
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

        void Render()
        {
            bool isList = mode == "list";
            dots.Visibility = !isList && !flashing ? Visibility.Visible : Visibility.Collapsed;
            flashLine.Visibility = !isList && flashing ? Visibility.Visible : Visibility.Collapsed;
            list.Visibility = isList ? Visibility.Visible : Visibility.Collapsed;
            if (isList) BuildList(); else BuildDots();

            requestBox.Visibility = hasRequest ? Visibility.Visible : Visibility.Collapsed;
            Fade(flashing || hasRequest ? 1.0 : (isList ? listOpacity : idleOpacity));
            bool show = isList || flashing || hasRequest || sessions.Length > 0;
            if (show && !IsVisible) Show();
            else if (!show && IsVisible) Hide();
        }

        void BuildDots()
        {
            dots.Children.Clear();
            foreach (object o in sessions)
            {
                var s = (Dictionary<string, object>)o;
                string[] look = Look(Str(s, "state"));
                dots.Children.Add(new TextBlock {
                    Text = look[0], Foreground = Paint(look[1]), FontFamily = Symbols, FontSize = 14,
                    Margin = new Thickness(3, 0, 3, 0), VerticalAlignment = VerticalAlignment.Center,
                });
            }
        }

        void BuildList()
        {
            list.Children.Clear();
            if (sessions.Length == 0)
            {
                list.Children.Add(new TextBlock { Text = "no Claude sessions", Foreground = Paint("#9E9E9E") });
                return;
            }
            foreach (object o in sessions)
            {
                var s = (Dictionary<string, object>)o;
                string[] look = Look(Str(s, "state"));
                bool speaking = s.ContainsKey("speaking") && Convert.ToBoolean(s["speaking"]);
                var row = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 1, 0, 1) };
                row.Children.Add(Cell(speaking ? Speaker : look[0], 24, Paint(look[1]), false, Symbols));
                row.Children.Add(Cell(Str(s, "name"), 150, Brushes.White, true, null));
                row.Children.Add(Cell(Str(s, "text"), 330, Paint("#DDDDDD"), false, null));
                row.Children.Add(Cell(Str(s, "meta"), 80, Paint("#9E9E9E"), false, null));
                if (speaking) row.Background = Paint("#33FFFFFF");
                list.Children.Add(row);
            }
        }

        static TextBlock Cell(string text, double width, Brush color, bool bold, FontFamily font)
        {
            var cell = new TextBlock {
                Text = text, Width = width, Foreground = color, TextTrimming = TextTrimming.CharacterEllipsis,
                FontWeight = bold ? FontWeights.SemiBold : FontWeights.Normal, VerticalAlignment = VerticalAlignment.Center,
            };
            if (font != null) cell.FontFamily = font;
            return cell;
        }

        // In dots mode a change expands to one solid line for a few seconds, then shrinks back.
        void Flash(Dictionary<string, object> msg)
        {
            string[] look = Look(Str(msg, "state"));
            flashLine.Inlines.Clear();
            flashLine.Inlines.Add(new Run(look[0] + "  ") { Foreground = Paint(look[1]), FontFamily = Symbols });
            flashLine.Inlines.Add(new Run(Str(msg, "name") + "  ") { FontWeight = FontWeights.SemiBold });
            flashLine.Inlines.Add(new Run(Str(msg, "text")) { Foreground = Paint("#DDDDDD") });
            flashing = true;
            flashTimer.Stop();
            flashTimer.Interval = TimeSpan.FromSeconds(Num(msg, "seconds", 4));
            flashTimer.Start();
            Render();
        }

        // A permission prompt stays on screen, solid, until it is answered: the hotkeys act on it.
        void ShowRequest(Dictionary<string, object> msg)
        {
            hasRequest = msg.ContainsKey("text");
            if (hasRequest)
            {
                string[] look = Look("needs_you");
                requestTitle.Inlines.Clear();
                requestTitle.Inlines.Add(new Run(look[0] + "  ") { Foreground = Paint(look[1]), FontFamily = Symbols });
                requestTitle.Inlines.Add(new Run(Str(msg, "name") + "  ") { FontWeight = FontWeights.SemiBold });
                requestTitle.Inlines.Add(new Run(Str(msg, "text")));
                requestDetail.Text = Str(msg, "detail");
                requestDetail.Visibility = requestDetail.Text.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
                requestKeys.Text = Str(msg, "keys");
            }
            Render();
        }

        void SetMode(string wanted)
        {
            mode = wanted == "toggle" ? (mode == "list" ? "dots" : "list") : (wanted == "list" ? "list" : "dots");
            Render();
            Send("mode", "mode", mode);
        }

        void Fade(double target)
        {
            if (opaque) target = 1.0;
            BeginAnimation(OpacityProperty, new DoubleAnimation(target, TimeSpan.FromMilliseconds(160)));
        }

        void Place()
        {
            Rect work = SystemParameters.WorkArea;
            bool right = corner.EndsWith("right"), bottom = corner.StartsWith("bottom");
            Left = right ? work.Right - ActualWidth - offsetX : work.Left + offsetX;
            Top = bottom ? work.Bottom - ActualHeight - offsetY : work.Top + offsetY;
        }

        // --- hotkeys --------------------------------------------------------------------------------

        void RegisterHotkeys(Dictionary<string, object> wanted)
        {
            foreach (int id in hotkeys.Keys) UnregisterHotKey(hwnd, id);
            hotkeys.Clear();
            int next = 1;
            foreach (KeyValuePair<string, object> entry in wanted)
            {
                string combo = Convert.ToString(entry.Value);
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
                if (vk == 0) { Error("hotkey not understood: " + combo); continue; }
                if (RegisterHotKey(hwnd, next, modifiers, vk)) hotkeys[next++] = entry.Key;
                else Error("hotkey " + combo + " is already taken by another program");
            }
        }

        IntPtr WndProc(IntPtr window, int message, IntPtr wParam, IntPtr lParam, ref bool handled)
        {
            string name;
            if (message == WM_HOTKEY && hotkeys.TryGetValue(wParam.ToInt32(), out name))
            {
                if (name == "toggle") SetMode("toggle");
                Send("hotkey", "name", name);
                handled = true;
            }
            return IntPtr.Zero;
        }

        // --- output to the hub ------------------------------------------------------------------

        void ReportBounds()
        {
            var reply = new Dictionary<string, object> { { "type", "bounds" }, { "visible", IsVisible } };
            if (IsVisible)
            {
                Point a = PointToScreen(new Point(0, 0)), b = PointToScreen(new Point(ActualWidth, ActualHeight));
                reply["x"] = (int)a.X; reply["y"] = (int)a.Y;
                reply["w"] = (int)(b.X - a.X); reply["h"] = (int)(b.Y - a.Y);
                reply["opacity"] = Opacity;
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

        static string[] Look(string state)
        {
            string[] look;
            return Looks.TryGetValue(state, out look) ? look : Looks["idle"];
        }

        static Brush Paint(string hex)
        {
            var brush = (Brush)new BrushConverter().ConvertFromInvariantString(hex);
            brush.Freeze();
            return brush;
        }

        static string Str(Dictionary<string, object> d, string key) { return Str(d, key, ""); }

        static string Str(Dictionary<string, object> d, string key, string fallback)
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
