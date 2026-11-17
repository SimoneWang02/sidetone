// The claude-speaks overlay: a glass bar with one status light per Claude session. Under the
// mouse a panel unfolds beside it with names and titles, and a speech bubble with a voice wave
// appears while a session talks. The bar can be dragged with the mouse. It only draws what the
// hub tells it to and reports hotkeys.
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
        public static readonly Color Amber = Color.FromRgb(0xFF, 0xB3, 0x00), Mic = Color.FromRgb(0xFF, 0x6E, 0x8A);
        public static readonly Brush Dim = Paint("#C8FFFFFF"), Faint = Paint("#8CFFFFFF"), MicInk = Paint("#FFFF8FA6"), LiveInk = Paint("#FFFF8FA7");
        // How many lines a sentence may take in a session's row of the details. With one, every row
        // is as high as its light and the bar never changes size; with more, a long sentence makes
        // its row higher and the bar stretches so that the lights stay level with their rows.
        public static int RowLines = 1;
        public static bool SignInLight = true;  // where push-to-talk's sign goes: in the session's light, or at the right of its line

        // The overlay's own words about push-to-talk move ("Release to send", "Working out what
        // you said...", "In focus", why nothing was sent; the author asked for "an animation on
        // the text", then for more of it and on all of these and not only the first):
        // shimmer = a glint of light runs along the words, then rests a moment |
        // pulse = the words breathe between soft and full | still. Your own words stay plain.
        // MicInk and LiveInk are only names for "this moving ink", in bold and in normal weight.
        // Its color is a soft white with a white glint, the color of no session: it was the
        // microphone's pink until the author saw it look like the name of a session whose own
        // color is nearly that pink, and chose to change the words and keep the name. A color of
        // your own (talk_text_color, "#RRGGBB") is used as it is, with a lighter glint.
        public static string TalkText = "shimmer";
        public static bool Motionless;  // for pictures
        static Color askInk = Color.FromArgb(0x8C, 0xFF, 0xFF, 0xFF), askGlint = Colors.White;
        static readonly LinearGradientBrush shine = MakeShine();
        static readonly SolidColorBrush breath = new SolidColorBrush(askInk), plain = new SolidColorBrush(Color.FromArgb(0xDC, 0xFF, 0xFF, 0xFF));

        static LinearGradientBrush MakeShine()
        {
            var brush = new LinearGradientBrush { MappingMode = BrushMappingMode.Absolute, StartPoint = new Point(-150, 0), EndPoint = new Point(0, 0) };
            brush.GradientStops.Add(new GradientStop(askInk, 0));
            brush.GradientStops.Add(new GradientStop(askGlint, 0.5));
            brush.GradientStops.Add(new GradientStop(askInk, 1));
            return brush;
        }

        public static void SetTalkColor(string hex)
        {
            Color soft = Color.FromArgb(0x8C, 0xFF, 0xFF, 0xFF), glint = Colors.White, full = Color.FromArgb(0xDC, 0xFF, 0xFF, 0xFF);
            try
            {
                if (hex != null && hex.Length > 0)
                {
                    soft = full = (Color)ColorConverter.ConvertFromString(hex);
                    glint = Mix(soft, Colors.White, 0.85);
                }
            }
            catch (Exception) { }  // not a color: the default
            askInk = soft;
            askGlint = glint;
            shine.GradientStops[0].Color = shine.GradientStops[2].Color = breath.Color = soft;
            shine.GradientStops[1].Color = glint;
            plain.Color = full;
        }

        // The ink for words that ask you to do something while the microphone is open.
        public static Brush MicLive
        {
            get { return Motionless || TalkText == "still" ? plain : TalkText == "pulse" ? breath : (Brush)shine; }
        }

        // How far the glint has to travel: about the width of the words it runs along.
        public static double GlintOver = 110;
        const double GlintWide = 150, GlintSpeed = 330, GlintRest = 0.3;  // pixels, pixels a second, seconds away

        public static void GlintFor(string words)
        {
            int longest = 0;
            foreach (string line in (words ?? "").Split('\n')) longest = Math.Max(longest, line.Length);
            GlintOver = Math.Max(60, Math.Min(300, longest * 7.2));
        }

        // One frame of that motion. The glint crosses the words at one speed whatever their length,
        // and is back a moment after it left.
        public static void MoveMicInk(double now)
        {
            if (Motionless) return;
            if (TalkText == "pulse") breath.Color = Mix(askInk, askGlint, 0.5 - 0.5 * Math.Cos(now * 2 * Math.PI / 1.4));
            else if (TalkText == "shimmer")
            {
                double travel = GlintOver + GlintWide, takes = travel / GlintSpeed;
                double at = -GlintWide + travel * Clamp((now % (takes + GlintRest)) / takes);  // left edge of the glint, in pixels from the start of the line
                shine.StartPoint = new Point(at, 0);
                shine.EndPoint = new Point(at + GlintWide, 0);
            }
        }

        public static Color Mix(Color a, Color b, double share)
        {
            return Color.FromArgb((byte)(a.A + (b.A - a.A) * share), (byte)(a.R + (b.R - a.R) * share),
                                  (byte)(a.G + (b.G - a.G) * share), (byte)(a.B + (b.B - a.B) * share));
        }

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

        public static double Clamp(double x) { return x < 0 ? 0 : x > 1 ? 1 : x; }

        // Fast at first, soft landing.
        public static double EaseOut(double x) { x = 1 - Clamp(x); return 1 - x * x * x; }

        // Like EaseOut, but goes a little past the end and settles back.
        public static double Overshoot(double x) { x = Clamp(x) - 1; return 1 + 2.4 * x * x * x + 1.4 * x * x; }

        // Moves a value toward its goal by the share that fits the time passed; true while still moving.
        public static bool Approach(ref double value, double goal, double rate, double dt)
        {
            if (Math.Abs(goal - value) < 0.004) { value = goal; return false; }
            value += (goal - value) * (1 - Math.Exp(-rate * dt));
            return true;
        }

        // A session's own color, as the hub names it ("#8AB4FF"); white when there is none.
        public static Brush Named(string hex)
        {
            try { return hex.Length > 0 ? Paint(hex) : Brushes.White; }
            catch (Exception) { return Brushes.White; }
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
        public static readonly Brush AmberEdge = Paint("#FFFFB300"), BrightEdge = Paint("#D0FFFFFF");
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

    // The round status light of one session. It pops when the state changes, sends out a ring
    // when a turn ends or needs you, grows a little under the mouse, and becomes five bars that
    // follow the voice while the session speaks. It can also carry push-to-talk's sign: your
    // own voice as bars while it listens, then dots, a paper plane, or a struck-out microphone.
    class Orb : FrameworkElement
    {
        public const double Size = 36;
        static readonly double[] Weights = { 0.5, 0.8, 1.0, 0.8, 0.5 };
        public string State = "idle", Sign = "";  // Sign: where push-to-talk stands, while it is about this session and shown here
        public bool Speaking;
        public Wave Wave, Listening;  // Listening: your own voice, while you hold the talk key for this session
        public double Born = Ui.Now, Changed = -10, Hot, SignSince;

        public Orb() { Width = Height = Size; IsHitTestVisible = false; }

        public void ShowSign(string kind)
        {
            if (kind == Sign) return;
            Sign = kind;
            SignSince = Ui.Now;
        }

        // While you speak the bars already say it; every later step takes the light over.
        bool Signed { get { return Sign.Length > 0 && Sign != "mic" && Listening == null; } }

        // Whether it has to be drawn again on the next frame.
        public bool Moving
        {
            get
            {
                double t = Ui.Now;
                if (Signed && (Sign == "dots" || t - SignSince < 0.5)) return true;
                return Speaking || Listening != null || State == "working" || State == "needs_you" || t - Changed < 0.8 || t - Born < 0.45;
            }
        }

        protected override void OnRender(DrawingContext dc)
        {
            double t = Ui.Now, age = t - Changed;
            var c = new Point(Size / 2, Size / 2);
            bool signed = Signed;
            Color tint = signed ? (Sign == "sent" ? Ui.Tint("done") : Sign == "failed" ? Ui.Tint("failed") : Ui.Mic) : Listening != null ? Ui.Mic : Ui.Tint(State);
            Wave wave = Listening ?? Wave;
            double bump = age < 0.4 ? 0.2 * Math.Sin(Math.PI * age / 0.4) : 0;
            double scale = Ui.Overshoot((t - Born) / 0.4) * (1 + bump + 0.14 * Hot);
            dc.PushTransform(new ScaleTransform(scale, scale, c.X, c.Y));
            if (age < 0.8 && Listening == null && (signed || (!Speaking && State != "idle" && State != "working")))
            {
                double ring = Ui.EaseOut(age / 0.8);  // a ring that spreads and fades
                dc.DrawEllipse(null, Ui.Line(tint, 0.7 * (1 - ring), 2), c, 13 + 9 * ring, 13 + 9 * ring);
            }
            if (signed)
            {
                dc.DrawEllipse(Ui.Alpha(tint, 0.30), Ui.Line(tint, 0.95, 1.5), c, 13, 13);
                Badge.Draw(dc, Sign, c.X, c.Y, t, t - SignSince, true);
                dc.Pop();
                return;
            }
            if (Speaking || Listening != null)
            {
                double level = wave.At(t - Wave.Lag);
                dc.DrawEllipse(Ui.Alpha(tint, 0.10 + 0.22 * level), null, c, 13.5 + 4 * level, 13.5 + 4 * level);
                dc.DrawEllipse(Ui.Alpha(tint, 0.30), Ui.Line(tint, 0.95, 1.5), c, 13, 13);
                for (int i = 0; i < 5; i++)
                {
                    double h = 3 + 17 * Weights[i] * wave.At(t - Wave.Lag - Math.Abs(i - 2) * 0.07);
                    dc.DrawRoundedRectangle(Brushes.White, null, new Rect(c.X + (i - 2) * 4.4 - 1.3, c.Y - h / 2, 2.6, h), 1.3, 1.3);
                }
                dc.Pop();
                return;
            }
            switch (State)
            {
                case "working":
                {
                    dc.DrawEllipse(Ui.Alpha(tint, 0.14), Ui.Line(tint, 0.28, 2), c, 12, 12);
                    // The arc runs round and breathes between short and long.
                    double a = t * 4.6, b = a + 1.5 + 0.9 * Math.Sin(t * 2.1);
                    var arc = new StreamGeometry();
                    using (StreamGeometryContext g = arc.Open())
                    {
                        g.BeginFigure(new Point(c.X + 12 * Math.Cos(a), c.Y + 12 * Math.Sin(a)), false, false);
                        g.ArcTo(new Point(c.X + 12 * Math.Cos(b), c.Y + 12 * Math.Sin(b)), new Size(12, 12), 0, false, SweepDirection.Clockwise, true, false);
                    }
                    dc.DrawGeometry(null, Ui.Line(tint, 1, 2.2), arc);
                    double beat = 3 + 0.5 * Math.Sin(t * 4.2);
                    dc.DrawEllipse(Ui.Alpha(tint, 0.95), null, c, beat, beat);
                    break;
                }
                case "needs_you":
                {
                    double pulse = 0.5 + 0.5 * Math.Sin(t * 4.5);
                    dc.DrawEllipse(Ui.Alpha(tint, 0.14 * pulse), null, c, 13 + 4.5 * pulse, 13 + 4.5 * pulse);
                    dc.DrawEllipse(Ui.Alpha(tint, 0.38 + 0.30 * pulse), Ui.Line(tint, 1, 1.5), c, 13, 13);
                    dc.DrawLine(Ui.Line(Colors.White, 1, 2.6), new Point(c.X, c.Y - 6.5), new Point(c.X, c.Y + 1.5));
                    dc.DrawEllipse(Brushes.White, null, new Point(c.X, c.Y + 6.3), 1.6, 1.6);
                    break;
                }
                case "done":
                {
                    dc.DrawEllipse(Ui.Alpha(tint, 0.26), Ui.Line(tint, 0.95, 1.5), c, 13, 13);
                    // The check is drawn stroke by stroke when the turn ends.
                    double drawn = Ui.EaseOut(age / 0.35), first = Math.Min(1, drawn / 0.4), second = Ui.Clamp((drawn - 0.4) / 0.6);
                    Pen pen = Ui.Line(Colors.White, 0.95, 2.3);
                    Point p0 = new Point(c.X - 5.6, c.Y + 0.4), p1 = new Point(c.X - 1.8, c.Y + 4.4), p2 = new Point(c.X + 5.8, c.Y - 4.2);
                    dc.DrawLine(pen, p0, new Point(p0.X + (p1.X - p0.X) * first, p0.Y + (p1.Y - p0.Y) * first));
                    if (second > 0) dc.DrawLine(pen, p1, new Point(p1.X + (p2.X - p1.X) * second, p1.Y + (p2.Y - p1.Y) * second));
                    break;
                }
                case "failed":
                {
                    dc.DrawEllipse(Ui.Alpha(tint, 0.30), Ui.Line(tint, 0.95, 1.5), c, 13, 13);
                    double reach = 4.6 * Ui.EaseOut(age / 0.3);
                    Pen pen = Ui.Line(Colors.White, 0.95, 2.3);
                    dc.DrawLine(pen, new Point(c.X - reach, c.Y - reach), new Point(c.X + reach, c.Y + reach));
                    dc.DrawLine(pen, new Point(c.X + reach, c.Y - reach), new Point(c.X - reach, c.Y + reach));
                    break;
                }
                default:
                    dc.DrawEllipse(Ui.Alpha(tint, 0.08), Ui.Line(tint, 0.65, 1.5), c, 12, 12);
                    dc.DrawEllipse(Ui.Alpha(tint, 0.65), null, c, 2.5, 2.5);
                    break;
            }
            dc.Pop();
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

    // A small sign for where push-to-talk stands: a microphone while it listens, three moving
    // dots while the words are worked out or wait to go, a paper plane once they are sent, a
    // cross when nothing went out. It is drawn inside the session's light (see Orb), or by
    // this element at the right of the session's line (the "talk_sign" setting).
    class Badge : FrameworkElement
    {
        public string Kind = "";  // "", mic, dots, sent, failed
        public double Since;

        public Badge() { Width = 20; Height = 18; IsHitTestVisible = false; VerticalAlignment = VerticalAlignment.Center; HorizontalAlignment = HorizontalAlignment.Right; }

        public void Show(string kind)
        {
            if (kind == Kind) return;
            Kind = kind;
            Since = Ui.Now;
            settled = false;
            Visibility = kind.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
            InvalidateVisual();
        }

        bool settled;  // drawn at least once after its entrance was over

        // Whether it has to be drawn again on the next frame.
        public bool Moving { get { return Kind == "mic" || Kind == "dots" || (Kind.Length > 0 && !settled); } }

        protected override void OnRender(DrawingContext dc)
        {
            double age = Ui.Now - Since;
            settled = age >= 0.45;
            Draw(dc, Kind, Width / 2, Height / 2, Ui.Now, age, false);
        }

        // The sign itself, around (cx, cy). At the right of a line it is in color; inside a
        // session's light, which has the color already, it is white and a little smaller, and
        // "nothing went out" is a struck-out microphone, since a plain cross there means that
        // the session failed.
        public static void Draw(DrawingContext dc, string kind, double cx, double cy, double t, double age, bool inLight)
        {
            double pop = Ui.Overshoot(age / 0.35) * (inLight ? 0.9 : 1);
            dc.PushTransform(new ScaleTransform(pop, pop, cx, cy));
            switch (kind)
            {
                case "mic":
                {
                    double beat = 0.75 + 0.25 * Math.Sin(t * 5);
                    Microphone(dc, cx, cy, Ui.Alpha(inLight ? Colors.White : Ui.Mic, beat));
                    break;
                }
                case "dots":
                    for (int i = 0; i < 3; i++)
                    {
                        double up = Math.Max(0, Math.Sin(t * 6 - i * 0.9));
                        dc.DrawEllipse(Ui.Alpha(Colors.White, 0.45 + 0.5 * up), null, new Point(cx + (i - 1) * 6, cy + 2 - 4 * up), 2, 2);
                    }
                    break;
                case "sent":
                {
                    // A paper plane that flies in from behind. Its three corners are equally far
                    // from the middle and it is the same on both sides of its line of flight, so
                    // it sits in the middle of a round light.
                    double back = (1 - Ui.EaseOut(age / 0.4)) * -9;
                    Color ink = inLight ? Colors.White : Ui.Tint("done");
                    Point nose = Aim(cx, cy, 9 + back, 0), notch = Aim(cx, cy, -2.6 + back, 0);
                    var plane = new StreamGeometry();
                    using (StreamGeometryContext g = plane.Open())
                    {
                        g.BeginFigure(nose, true, true);
                        g.LineTo(Aim(cx, cy, -6.2 + back, -6.5), true, true);
                        g.LineTo(notch, true, true);
                        g.LineTo(Aim(cx, cy, -6.2 + back, 6.5), true, true);
                    }
                    dc.DrawGeometry(Ui.Alpha(ink, 0.35), Ui.Line(ink, 1, 1.5), plane);
                    dc.DrawLine(Ui.Line(ink, 1, 1.5), notch, nose);
                    break;
                }
                case "failed":
                {
                    if (inLight)
                    {
                        Microphone(dc, cx, cy, Ui.Alpha(Colors.White, 0.6));
                        double reach = 7.5 * Ui.EaseOut(age / 0.3);  // the stroke through it is drawn last
                        dc.DrawLine(Ui.Line(Ui.Tint("failed"), 1, 5), new Point(cx - reach, cy - reach), new Point(cx + reach, cy + reach));
                        dc.DrawLine(Ui.Line(Colors.White, 1, 2), new Point(cx - reach, cy - reach), new Point(cx + reach, cy + reach));
                        break;
                    }
                    Pen pen = Ui.Line(Ui.Tint("failed"), 1, 2);
                    dc.DrawLine(pen, new Point(cx - 4.5, cy - 4.5), new Point(cx + 4.5, cy + 4.5));
                    dc.DrawLine(pen, new Point(cx + 4.5, cy - 4.5), new Point(cx - 4.5, cy + 4.5));
                    break;
                }
            }
            dc.Pop();
        }

        // A point given along and across the paper plane's line of flight, which goes up to the right.
        static Point Aim(double cx, double cy, double along, double across)
        {
            const double Cos = 0.8192, Sin = -0.5736;  // 35 degrees up
            return new Point(cx + along * Cos - across * Sin, cy + along * Sin + across * Cos);
        }

        static void Microphone(DrawingContext dc, double cx, double cy, Brush ink)
        {
            var pen = new Pen(ink, 1.6) { StartLineCap = PenLineCap.Round, EndLineCap = PenLineCap.Round };
            dc.DrawRoundedRectangle(ink, null, new Rect(cx - 2.6, cy - 8, 5.2, 9.5), 2.6, 2.6);  // the capsule
            var cup = new StreamGeometry();
            using (StreamGeometryContext g = cup.Open())
            {
                g.BeginFigure(new Point(cx - 5.2, cy - 1.5), false, false);
                g.ArcTo(new Point(cx + 5.2, cy - 1.5), new Size(5.2, 5.2), 0, false, SweepDirection.Counterclockwise, true, false);
            }
            dc.DrawGeometry(null, pen, cup);
            dc.DrawLine(pen, new Point(cx, cy + 3.7), new Point(cx, cy + 7));
            dc.DrawLine(pen, new Point(cx - 3, cy + 7), new Point(cx + 3, cy + 7));
        }
    }

    // One see-through piece of the overlay. Windows blurs what is behind a whole window and rounds
    // its corners, and cannot do that for a free shape, so every piece of glass is its own window
    // exactly as big as what it shows. Clicks pass through and it never takes focus.
    //
    // A piece made with a width "unfolds": its height is moved, frame by frame, between nothing
    // and the height of what it holds. The blur cannot fade (it is all or nothing), so growing the
    // window is what makes the glass appear smoothly. Its top left corner stays put while it
    // grows, which is the only way a see-through window resizes without a flicker.
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
        public readonly bool Unfolds;
        public double Goal, Tall, Full;  // unfolding: the height wanted, the height now, the last open height
        FrameworkElement body;
        double speed;

        public Glass(double unfoldingWidth)
        {
            Unfolds = unfoldingWidth > 0;
            WindowStyle = WindowStyle.None;
            AllowsTransparency = true;
            Background = Brushes.Transparent;
            Topmost = true;
            ShowInTaskbar = false;
            ShowActivated = false;
            Focusable = false;
            IsHitTestVisible = false;
            ResizeMode = ResizeMode.NoResize;
            if (Unfolds) { Width = unfoldingWidth; Height = 1; MinHeight = 0; Panel.ClipToBounds = true; }
            else SizeToContent = SizeToContent.WidthAndHeight;
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

        public FrameworkElement Body
        {
            get { return body; }
            set { body = value; body.VerticalAlignment = VerticalAlignment.Top; Panel.Child = body; }
        }

        // How tall the window is when fully open: what it holds, plus the edge.
        public double Natural()
        {
            body.UpdateLayout();  // so a change made a moment ago (new text, a hidden section) counts
            body.Measure(new Size(Width - 2, double.PositiveInfinity));
            return Math.Ceiling(body.DesiredSize.Height) + 2;
        }

        // One step of unfolding or folding away; true while it is still moving. It opens like a
        // soft spring (it starts gently, arrives quickly, goes a touch too far and settles) and
        // folds away without the bounce.
        public bool Step(double dt, bool instantly)
        {
            if (Goal > 0) Full = Goal;
            if (Goal > 0 && !IsVisible) { Tall = Math.Min(Tall, Goal); speed = 0; Height = Math.Max(1, Tall); Show(); }
            bool moving = Math.Abs(Goal - Tall) >= 0.4 || Math.Abs(speed) > 5;
            if (!moving || instantly) { Tall = Goal; speed = 0; }
            else
            {
                double pull = Goal > 0 ? 230 : 420, drag = Goal > 0 ? 22 : 41;
                for (double left = dt; left > 0; left -= 0.004)
                {
                    double h = Math.Min(0.004, left);
                    speed += ((Goal - Tall) * pull - speed * drag) * h;
                    Tall += speed * h;
                    if (Tall < 0) { Tall = 0; speed = 0; }
                }
            }
            if (Math.Abs(Height - Math.Max(1, Tall)) > 0.01) Height = Math.Max(1, Tall);
            if (Goal == 0 && Tall == 0 && IsVisible) Hide();
            return moving && !instantly;
        }

        // How far open it is, from 0 to 1.
        public double Open { get { return Full > 0 ? Ui.Clamp(Tall / Full) : 0; } }

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

    // One session: its status light in the bar, and its line in the panel (name, a short title,
    // and what it is doing or saying).
    class Row
    {
        public const double High = 44;
        public readonly Grid Light = new Grid { Width = High, Height = High };
        public readonly Orb Orb = new Orb();
        public readonly Grid Text = new Grid { MinHeight = High };
        public readonly WaveStrip Strip = new WaveStrip();
        public readonly Wave Wave;
        public readonly TranslateTransform Slide = new TranslateTransform();
        readonly Border glow = new Border { CornerRadius = new CornerRadius(6), Background = Ui.Paint("#FFFFFF"), Opacity = 0 };
        readonly Grid row2 = new Grid();
        readonly StackPanel words = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
        readonly TextBlock line1 = new TextBlock(), line2 = new TextBlock(), meta = new TextBlock();
        public bool Speaking, Focus;
        public readonly Border Pip = new Border {  // a dash of its color under the light, where rows are not beside their lights
            Width = 16, Height = 3, CornerRadius = new CornerRadius(1.5), VerticalAlignment = VerticalAlignment.Bottom,
            Margin = new Thickness(0, 0, 0, 1), Visibility = Visibility.Collapsed,
        };
        public string Name = "", Color = "", Title = "", State = "", FlashText, TalkKind, TalkText = "";  // TalkKind: null unless push-to-talk is about this session
        public readonly Badge Badge = new Badge { Visibility = Visibility.Collapsed };
        Brush talkInk = Brushes.White;  // white for your words, dim for a note, the microphone's color for what to do
        public double FlashUntil, Hot, Lit;
        string rowText = "", metaText = "";

        public Row(bool right, Wave wave)
        {
            Wave = Orb.Wave = Strip.Wave = wave;
            Strip.NewestRight = right;
            Light.Children.Add(Orb);
            Light.Children.Add(Pip);
            Strip.Margin = right ? new Thickness(8, 0, 0, 0) : new Thickness(0, 0, 8, 0);
            words.Margin = new Thickness(12, 5, 12, 6);
            words.RenderTransform = Slide;
            line1.TextTrimming = line2.TextTrimming = TextTrimming.CharacterEllipsis;
            line2.FontSize = meta.FontSize = 12;
            meta.Foreground = Ui.Faint;
            meta.FontFamily = Ui.Symbols;
            meta.Margin = new Thickness(8, 0, 0, 0);
            row2.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            row2.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            Grid.SetColumn(meta, 1);
            row2.Children.Add(line2);
            row2.Children.Add(meta);
            var row1 = new Grid();  // the name and title, and at the right the push-to-talk sign
            row1.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            row1.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            Grid.SetColumn(Badge, 1);
            row1.Children.Add(line1);
            row1.Children.Add(Badge);
            words.Children.Add(row1);
            words.Children.Add(row2);
            Text.Children.Add(glow);
            Text.Children.Add(Strip);
            Text.Children.Add(words);
        }

        public void Update(Dictionary<string, object> s)
        {
            bool was = Speaking;
            string before = State;
            Name = Overlay.Str(s, "name");
            Color = Overlay.Str(s, "color");
            Pip.Background = Ui.Named(Color);
            Title = Overlay.Str(s, "title");
            State = Orb.State = Overlay.Str(s, "state", "idle");
            Speaking = Orb.Speaking = s.ContainsKey("speaking") && Convert.ToBoolean(s["speaking"]);
            Focus = s.ContainsKey("target") && Convert.ToBoolean(s["target"]);
            if (before.Length > 0 && (before != State || was != Speaking)) Orb.Changed = Ui.Now;  // the light pops
            Wave.Synthetic = s.ContainsKey("synth") && Convert.ToBoolean(s["synth"]);
            if (Speaking && !was) Wave.Since = Ui.Now;
            if (!Speaking && was) Wave.Clear();
            Overlay.Heading(line1, Name, Title, Color);
            string text = Overlay.Str(s, "text");
            if (text != rowText && rowText.Length > 0 && !Saying)  // what it is doing changed: the new words fade in
                line2.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(0.15, 1, TimeSpan.FromMilliseconds(260)));
            rowText = text;
            metaText = Overlay.Str(s, "meta");
            Refresh();
            Orb.InvalidateVisual();
        }

        public bool Saying { get { return FlashText != null && (Speaking || Ui.Now < FlashUntil); } }

        // Something to read about it right now: what it says, or what you are saying to it.
        public bool Showing { get { return TalkKind != null || Saying; } }

        // Push-to-talk is about this session (which sign to show, the words under the name, and
        // whether those words are only a hint), or no longer (kind is null).
        public void SetTalk(string kind, string text, Brush ink, Wave mic)
        {
            bool changed = kind != TalkKind || text != TalkText || (Orb.Listening != null) != (mic != null);
            TalkKind = kind;
            TalkText = text ?? "";
            talkInk = ink;
            Orb.Listening = mic;
            changed |= (Ui.SignInLight ? Orb.Sign : Badge.Kind) != (kind ?? "");  // the sign moved between light and line
            Orb.ShowSign(Ui.SignInLight ? kind ?? "" : "");
            Badge.Show(Ui.SignInLight ? "" : kind ?? "");
            if (changed) { Orb.Changed = Ui.Now; Refresh(); }
        }

        // The second line is the sentence being spoken (or just shown) while there is one,
        // otherwise what the session is doing.
        public void Refresh()
        {
            bool saying = Showing, talk = TalkKind != null;
            line2.Text = talk ? TalkText : saying ? FlashText : rowText;
            line2.TextWrapping = saying && Ui.RowLines > 1 ? TextWrapping.Wrap : TextWrapping.NoWrap;
            line2.MaxHeight = 16.7 * Ui.RowLines;
            bool live = talkInk == Ui.MicInk || talkInk == Ui.LiveInk;
            if (talk && live) Ui.GlintFor(TalkText);
            line2.Foreground = talk ? (live ? Ui.MicLive : talkInk) : saying ? Brushes.White : Ui.Dim;
            line2.FontWeight = talk && talkInk == Ui.MicInk ? FontWeights.SemiBold : FontWeights.Normal;
            meta.Text = metaText;
            meta.Visibility = saying || metaText.Length == 0 ? Visibility.Collapsed : Visibility.Visible;
            row2.Visibility = line2.Text.Length == 0 && meta.Visibility != Visibility.Visible ? Visibility.Collapsed : Visibility.Visible;
            Strip.Wave = Orb.Listening ?? Wave;
            Strip.Tint = Orb.Listening != null ? Ui.Mic : Ui.Tint(State);
            Strip.Visibility = Speaking || Orb.Listening != null ? Visibility.Visible : Visibility.Collapsed;
        }

        // The soft highlight behind the line: under the mouse, while it is being said, and
        // (fainter) on the session in focus, the one a spoken follow-up goes to.
        public bool Glow(double dt)
        {
            bool moving = Ui.Approach(ref Lit, Math.Max(Hot > 0.5 ? 0.11 : 0, Math.Max(Showing ? 0.085 : 0, Focus ? 0.06 : 0)), 14, dt);
            glow.Opacity = Lit;
            return moving;
        }
    }

    public class Overlay
    {
        const int WM_HOTKEY = 0x0312;
        const uint MOD_ALT = 1, MOD_CONTROL = 2, MOD_SHIFT = 4, MOD_WIN = 8, MOD_NOREPEAT = 0x4000;
        const uint MOUSEEVENTF_LEFTDOWN = 2, MOUSEEVENTF_LEFTUP = 4;
        const int VK_LBUTTON = 1, VK_RBUTTON = 2, SM_SWAPBUTTON = 23;
        const int WH_KEYBOARD_LL = 13, WM_KEYDOWN = 0x0100, WM_SYSKEYDOWN = 0x0104;
        const int WH_MOUSE_LL = 14, WM_MOUSEWHEEL = 0x020A, VK_SHIFT = 0x10, VK_CONTROL = 0x11, VK_MENU = 0x12, VK_LWIN = 0x5B, VK_RWIN = 0x5C, VK_RMENU = 0xA5;
        const int VK_LSHIFT = 0xA0, VK_RSHIFT = 0xA1, VK_LCONTROL = 0xA2, VK_RCONTROL = 0xA3, VK_LMENU = 0xA4;
        const double PanelWidth = 340, BubbleWidth = 340, Gap = 6, Wide = PanelWidth - 32;

        [DllImport("user32.dll")] static extern bool RegisterHotKey(IntPtr hwnd, int id, uint modifiers, uint vk);
        [DllImport("user32.dll")] static extern bool UnregisterHotKey(IntPtr hwnd, int id);
        [DllImport("user32.dll")] static extern short GetAsyncKeyState(int key);
        [DllImport("user32.dll")] static extern bool GetCursorPos(out CursorPoint point);
        [StructLayout(LayoutKind.Sequential)] struct CursorPoint { public int X; public int Y; }
        [DllImport("user32.dll")] static extern int GetSystemMetrics(int index);
        [DllImport("user32.dll")] static extern void keybd_event(byte key, byte scan, uint flags, UIntPtr extra);
        delegate IntPtr HookProc(int code, IntPtr wParam, IntPtr lParam);
        [DllImport("user32.dll")] static extern IntPtr SetWindowsHookEx(int kind, HookProc proc, IntPtr module, uint thread);
        [DllImport("user32.dll")] static extern bool UnhookWindowsHookEx(IntPtr hook);
        [DllImport("user32.dll")] static extern IntPtr CallNextHookEx(IntPtr hook, int code, IntPtr wParam, IntPtr lParam);
        [DllImport("kernel32.dll")] static extern IntPtr GetModuleHandle(string name);
        [StructLayout(LayoutKind.Sequential)] struct MouseHookData { public CursorPoint Point; public uint Data, Flags, Time; public IntPtr Extra; }
        [DllImport("user32.dll")] static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);

        readonly JavaScriptSerializer json = new JavaScriptSerializer();
        readonly TextWriter output;
        // The bar of lights, the panel that unfolds beside it, and the speech bubble.
        readonly Glass rail = new Glass(0), panel = new Glass(PanelWidth), bubble = new Glass(BubbleWidth);
        readonly StackPanel lights = new StackPanel { Margin = new Thickness(3) };
        // A soft frame that slides to the light of the session in focus.
        readonly Border selector = new Border {
            Width = 40, Height = 40, CornerRadius = new CornerRadius(11), Background = Ui.Paint("#26FFFFFF"), BorderBrush = Ui.Paint("#70FFFFFF"),
            BorderThickness = new Thickness(1), VerticalAlignment = VerticalAlignment.Top, Opacity = 0, IsHitTestVisible = false,
        };
        readonly TranslateTransform selectorAt = new TranslateTransform();
        readonly HookProc wheelProc, keyProc;
        IntPtr wheelHook, keyHook;
        int[] wheelKeys = { VK_CONTROL, VK_MENU };  // held together with the wheel to change the focus
        // Held to take hold of the bar with the mouse (drag it, turn the wheel on it). Without
        // them the mouse goes straight through the bar to what is underneath. Empty: any time.
        int[] dragKeys = { VK_CONTROL, VK_MENU };
        int wheelTurned;
        double wheelUntil, selectorY, selectorShown, heldSince;
        bool wheeling, keysOpen;
        readonly Grid spare = new Grid { Width = Row.High, Height = Row.High };  // a dim light shown when there is no session
        readonly StackPanel sections = new StackPanel { Margin = new Thickness(3) };
        readonly StackPanel rowsPanel = new StackPanel();
        readonly StackPanel requestBox = new StackPanel(), bannerBox = new StackPanel(), historyBox = new StackPanel();
        readonly StackPanel historyLines = new StackPanel();
        readonly TextBlock requestTitle = new TextBlock(), requestDetail = new TextBlock(), requestKeys = new TextBlock();
        readonly FontFamily requestMono = new FontFamily("Consolas");
        readonly TextBlock bannerTitle = new TextBlock(), bannerHint = new TextBlock();
        readonly TextBlock emptyLine = new TextBlock { Text = "No Claude sessions", Foreground = Ui.Faint, Margin = new Thickness(12, 13, 12, 13) };
        readonly TextBlock bubbleLine1 = new TextBlock(), bubbleLine2 = new TextBlock();
        readonly StackPanel bubbleWords = new StackPanel { Margin = new Thickness(14, 8, 14, 10) };
        readonly TranslateTransform bubbleSlide = new TranslateTransform();
        readonly WaveStrip bubbleStrip = new WaveStrip();
        readonly Badge bubbleBadge = new Badge { Visibility = Visibility.Collapsed };
        readonly Dictionary<string, Row> rows = new Dictionary<string, Row>();
        readonly List<Row> order = new List<Row>();  // the rows from top to bottom
        readonly Dictionary<string, Wave> waves = new Dictionary<string, Wave>();
        readonly Dictionary<string, KeyValuePair<string, double>> flashes = new Dictionary<string, KeyValuePair<string, double>>();
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
        uint talkKey, talkMods;  // the talk hotkey as claimed: its key, and its Ctrl/Alt/Shift/Win as MOD_ flags
        string keepTalk = "held";  // when the key hook is in: held (while those other keys are down) | always | off
        bool holding;  // the talk key is being held
        bool taken;  // the press that began this hold was kept from Windows, so its release must be too
        bool repeated;  // the held key has repeated, so its repeats can tell us it is still down
        double lastRepeat;
        // While you talk, the Ctrl and Alt of the talk hotkey are hidden from other programs (see MaskKeys).
        bool freeKeys = true;  // overlay.talk_frees_keys
        readonly HashSet<int> masked = new HashSet<int>();  // those keys: still held as far as we know, though Windows was told they are up
        double maskedUntil;  // once talking is over, how long we go on believing that without a sign of it
        const double MaskGrace = 3;
        const long Ours = 0x43535031;  // marks the key events the overlay sends itself
        readonly Dictionary<string, uint[]> claims = new Dictionary<string, uint[]>();  // hotkey name -> its key and MOD_ flags
        readonly IntPtr hwnd;

        object[] sessions = new object[0];
        object[] history = new object[0];
        bool historyAll;  // the history shows every session's lines, not only those of the one under the mouse
        // The mouse alone on the bar brings the details out. `hover: keys` turns that off, for a
        // bar that must not answer to a mouse passing over it in a game: then only holding
        // Ctrl+Alt brings them out. The author asked for that as the default, tried to picture
        // it and took it back ("I like hovering ... opening up its details"), so it is a choice.
        bool hoverOpens = true;
        string historyOf = "";  // the session whose lines the history shows: the one the mouse was on last
        int monitor, insideTicks, outsideTicks;  // monitor: 0 = primary, 1.. = the others in Windows' order
        bool moving, dragging, catching, hover, peek, peekForced, opaque, hasRequest, hasBanner, running, still;
        string mode = "dots", corner = "top-right", glass = "blur", bubbleShows = "";
        double offsetX = 12, offsetY = 96, idleOpacity = 0.9, listOpacity = 1.0, lastFade = -1;
        double lastFrame, openedAt, bubbleAt, passUntil;
        int grabX, grabY;  // where on the bar the mouse took hold
        int frames;
        bool inFrame;
        int[] grabbedAt = new int[4];
        Row talker, hot;  // the session the speech bubble belongs to; the one under the mouse
        // How the sessions are laid out: "bar" (a column of lights at the side of the screen, with
        // the details beside it) or "island" (a row of lights at the top middle of the screen, with
        // everything else dropping down from it).
        string layout = "bar";
        bool Island { get { return layout == "island"; } }
        // The island keeps its own place: where its middle is across the screen (0 to 1), and how
        // far down from the top. In the lower half of the screen everything opens upward from it.
        double islandX = 0.5, islandY = 10;
        bool islandLow;
        bool Low { get { return Island ? islandLow : corner.StartsWith("bottom"); } }
        bool handling;
        readonly Queue<string> waiting = new Queue<string>();
        // Push-to-talk: what is going on (listening, transcribing, sent, ...), for which session,
        // the words, and your own voice as the microphone hears it.
        readonly Wave mic = new Wave();
        string talkState = "", talkName = "", talkText = "", talkHint = "";
        double talkUntil;

        Overlay(TextWriter output)
        {
            this.output = output;
            hwnd = rail.Handle;
            spare.Children.Add(new Orb());
            selector.RenderTransform = selectorAt;
            var layers0 = new Grid();
            layers0.Children.Add(selector);
            layers0.Children.Add(lights);
            rail.Panel.Child = layers0;
            wheelProc = OnMouse;  // kept in a field so it stays alive while Windows holds it
            keyProc = OnKey;
            rail.MouseWheel += delegate(object sender, MouseWheelEventArgs e) { Wheel(e.Delta); };
            rail.Cursor = Cursors.SizeAll;

            requestTitle.TextWrapping = requestKeys.TextWrapping = requestDetail.TextWrapping = TextWrapping.Wrap;
            requestTitle.MaxHeight = 54;
            requestTitle.TextTrimming = requestDetail.TextTrimming = TextTrimming.CharacterEllipsis;
            requestDetail.FontFamily = requestMono;
            requestDetail.Foreground = Ui.Dim;
            requestDetail.Margin = new Thickness(0, 4, 0, 4);
            requestKeys.Foreground = Ui.AmberEdge;
            Section(requestBox, requestTitle, requestDetail, requestKeys);
            bannerTitle.TextWrapping = bannerHint.TextWrapping = TextWrapping.Wrap;
            bannerHint.Foreground = Ui.Faint;
            bannerHint.Margin = new Thickness(0, 2, 0, 0);
            Section(bannerBox, bannerTitle, bannerHint);
            Section(historyBox, historyLines);
            panel.Body = sections;
            Stack();

            // The speech bubble: who is talking, the sentence, and the voice flowing behind it.
            bubbleLine1.TextTrimming = bubbleLine2.TextTrimming = TextTrimming.CharacterEllipsis;
            bubbleLine2.TextWrapping = TextWrapping.Wrap;
            bubbleLine2.MaxHeight = 68;  // four lines
            bubbleLine2.Margin = new Thickness(0, 2, 0, 0);
            bubbleWords.RenderTransform = bubbleSlide;
            var bubbleRow1 = new Grid();
            bubbleRow1.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            bubbleRow1.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            Grid.SetColumn(bubbleBadge, 1);
            bubbleRow1.Children.Add(bubbleLine1);
            bubbleRow1.Children.Add(bubbleBadge);
            bubbleWords.Children.Add(bubbleRow1);
            bubbleWords.Children.Add(bubbleLine2);
            var layers = new Grid();
            layers.Children.Add(bubbleStrip);
            layers.Children.Add(bubbleWords);
            bubble.Body = layers;

            rail.SizeChanged += delegate { Place(); };
            bannerTimer.Tick += delegate { bannerTimer.Stop(); hasBanner = false; Render(); };
            // Clicks pass through, so "the mouse is on me" is found by watching where the cursor is.
            hoverTimer.Interval = TimeSpan.FromMilliseconds(30);
            hoverTimer.Tick += delegate { WatchWheelKeys(); WatchTalkKeys(); WatchCursor(); };
            moveTimer.Tick += delegate { EndMove(); };
            rail.MouseLeftButtonDown += delegate(object sender, MouseButtonEventArgs e) { BeginDrag(e.GetPosition(rail)); };
            // Hold-to-talk: a hotkey only reports the press, so watch the key until it comes back up.
            holdTimer.Interval = TimeSpan.FromMilliseconds(30);
            holdTimer.Tick += delegate { if (!Down((int)heldKey)) EndHold(); };
            // Other always-on-top windows (and some games) push us down; climb back regularly.
            topTimer.Interval = TimeSpan.FromSeconds(2);
            topTimer.Tick += delegate { rail.Raise(); panel.Raise(); bubble.Raise(); };

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

        // Creating or showing a window can let the next message in before this one is done,
        // which would change the list of sessions under the feet of whoever is walking it.
        // So a message that arrives meanwhile waits its turn.
        void Handle(string line)
        {
            if (handling) { waiting.Enqueue(line); return; }
            handling = true;
            try
            {
                HandleOne(line);
                while (waiting.Count > 0) HandleOne(waiting.Dequeue());
            }
            finally { handling = false; }
        }

        void HandleOne(string line)
        {
            Dictionary<string, object> msg;
            try { msg = (Dictionary<string, object>)json.DeserializeObject(line); }
            catch (Exception e) { Error("bad message: " + e.Message); return; }

            switch (Str(msg, "type"))
            {
                case "config":
                    string was = corner;
                    corner = Str(msg, "corner", corner);
                    offsetX = Num(msg, "offset_x", offsetX);
                    offsetY = Num(msg, "offset_y", offsetY);
                    idleOpacity = Num(msg, "opacity", idleOpacity);
                    listOpacity = Num(msg, "list_opacity", listOpacity);
                    monitor = (int)Num(msg, "monitor", monitor);
                    opaque = msg.ContainsKey("opaque") && Convert.ToBoolean(msg["opaque"]);
                    still = Ui.Motionless = msg.ContainsKey("still") && Convert.ToBoolean(msg["still"]);
                    if (msg.ContainsKey("talk_text")) Ui.TalkText = Str(msg, "talk_text");
                    if (msg.ContainsKey("talk_text_color")) Ui.SetTalkColor(Str(msg, "talk_text_color"));
                    glass = Str(msg, "glass", glass);
                    islandX = Num(msg, "island_x", islandX);
                    islandY = Num(msg, "island_y", islandY);
                    string wanted = Str(msg, "layout", layout);
                    if (wanted != "island") wanted = "bar";
                    if (wanted != layout) { layout = wanted; ApplyLayout(); RegisterHotkeys(); }  // other arrow keys now
                    if (msg.ContainsKey("focus_wheel")) wheelKeys = Keys(Str(msg, "focus_wheel"));
                    if (msg.ContainsKey("drag_keys")) dragKeys = Keys(Str(msg, "drag_keys"));
                    Ui.RowLines = Math.Max(1, Math.Min(3, (int)Num(msg, "row_lines", Ui.RowLines)));
                    if (msg.ContainsKey("talk_sign")) Ui.SignInLight = Str(msg, "talk_sign") != "line";
                    keepTalk = Str(msg, "keep_talk_key", keepTalk);
                    if (msg.ContainsKey("history")) historyAll = Str(msg, "history") == "all";
                    if (msg.ContainsKey("hover")) hoverOpens = Str(msg, "hover") != "keys";
                    if (msg.ContainsKey("talk_frees_keys")) freeKeys = Convert.ToBoolean(msg["talk_frees_keys"]);
                    SetGlass();
                    if (was != corner) { ForgetRows(); Stack(); }  // the panel changes sides, or its order
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
                case "talk":
                    Talk(msg);
                    break;
                case "mic":
                    AddLevels(mic, msg);
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
                case "peek":  // open the panel and the history without a mouse (for checking how it looks)
                    peekForced = hover = msg.ContainsKey("on") && Convert.ToBoolean(msg["on"]);
                    peek = peekForced && mode == "list";
                    historyOf = Str(msg, "over", "");  // as if the mouse were on that session's row
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
            panel.Look(kind);
            bubble.Look(kind);
        }

        // A different layout: start again from nothing, so every light lands in its new home.
        void ApplyLayout()
        {
            ForgetRows();
            lights.Orientation = Island ? Orientation.Horizontal : Orientation.Vertical;
            selector.HorizontalAlignment = Island ? HorizontalAlignment.Left : HorizontalAlignment.Center;
            selector.VerticalAlignment = Island ? VerticalAlignment.Center : VerticalAlignment.Top;
            selectorAt.X = selectorAt.Y = 0;
            selectorShown = 0;
            hover = peek = false;
            if (catching) { catching = false; rail.CatchMouse(false); }
            if (rail.IsVisible) rail.Hide();
            Edge();
        }

        // A block of text in the panel, with a hairline between it and the rows.
        static void Section(StackPanel box, params UIElement[] children)
        {
            var body = new StackPanel { Margin = new Thickness(12, 8, 12, 9), Width = Wide };
            foreach (UIElement child in children) body.Children.Add(child);
            box.Children.Add(new Border { Height = 1, Background = Ui.Paint("#30FFFFFF"), Margin = new Thickness(8, 0, 8, 0) });
            box.Children.Add(body);
        }

        // The rows sit level with their lights, so everything else goes below them, or above
        // them when the bar hangs from the bottom of the screen.
        void Stack()
        {
            bool bottom = Low;
            var parts = new List<UIElement> { rowsPanel, emptyLine, requestBox, bannerBox, historyBox };
            if (bottom) parts.Reverse();
            sections.Children.Clear();
            foreach (UIElement part in parts) sections.Children.Add(part);
            foreach (StackPanel box in new[] { requestBox, bannerBox, historyBox })
            {
                UIElement line = box.Children[0] is Border ? box.Children[0] : box.Children[1];
                box.Children.Remove(line);
                if (bottom) box.Children.Add(line); else box.Children.Insert(0, line);
            }
        }

        // "name   title": the name in bold and in the session's own color, the title in white.
        internal static void Heading(TextBlock line, string name, string title, string color)
        {
            line.Inlines.Clear();
            line.Inlines.Add(new Run(name) { FontWeight = FontWeights.SemiBold, Foreground = Ui.Named(color) });
            if (title.Length > 0) line.Inlines.Add(new Run("   " + title) { Foreground = Ui.Dim });
        }

        // The panel (names, titles, what each session is doing) is out in list mode, under the
        // mouse, while Ctrl+Alt is held, and while there is something to ask or show. Otherwise there are only the lights.
        bool IsOpen() { return !dragging && (mode == "list" || hover || moving || hasRequest || hasBanner || keysOpen || Ui.Now < wheelUntil); }

        // Brings everything in line with what there is to show. What moves is then moved by Frame.
        void Render()
        {
            bool isList = mode == "list", open = IsOpen();
            SyncRows();
            requestBox.Visibility = hasRequest ? Visibility.Visible : Visibility.Collapsed;
            bannerBox.Visibility = hasBanner ? Visibility.Visible : Visibility.Collapsed;
            emptyLine.Visibility = sessions.Length == 0 ? Visibility.Visible : Visibility.Collapsed;
            bool showHistory = isList && peek && history.Length > 0;
            historyBox.Visibility = showHistory ? Visibility.Visible : Visibility.Collapsed;
            if (showHistory) BuildHistory();
            if (historyLines.Children.Count == 0) historyBox.Visibility = Visibility.Collapsed;  // that session has said nothing yet
            bool talking = talkState.Length > 0;
            foreach (Row row in order)
                if (talking && row.Name == talkName) row.SetTalk(TalkKind(), TalkWords(), TalkInk(), talkState == "listening" ? mic : null);
                else row.SetTalk(null, "", Brushes.White, null);
            bool show = isList || hasRequest || hasBanner || moving || talking || sessions.Length > 0;
            if (show && !rail.IsVisible) rail.Show();
            else if (!show && rail.IsVisible) rail.Hide();

            double goal = open && show ? panel.Natural() : 0;
            if (goal > 0 && panel.Goal == 0) openedAt = Ui.Now;  // the rows come in one after another from now
            panel.Goal = goal;
            // A row that says a long sentence is taller than a light; keep the two level (where
            // rows and lights sit side by side).
            foreach (Row row in order)
            {
                row.Pip.Visibility = Island ? Visibility.Visible : Visibility.Collapsed;
                row.Light.Height = !Island && goal > 0 && row.Text.DesiredSize.Height > Row.High + 4 ? row.Text.DesiredSize.Height : Row.High;
            }
            UpdateBubble(show);
            PlaceSides();
            Fade();
            Run(true);
        }

        // Keeps one row per session, in the hub's order, without rebuilding the ones that stay.
        void SyncRows()
        {
            bool right = corner.EndsWith("right");
            var names = new HashSet<string>();
            order.Clear();
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
                order.Add(row);
                names.Add(name);
            }
            foreach (string gone in new List<string>(rows.Keys))
                if (!names.Contains(gone)) { rows.Remove(gone); waves.Remove(gone); flashes.Remove(gone); }
            if (hot != null && !rows.ContainsValue(hot)) hot = null;
            bool same = rowsPanel.Children.Count == order.Count && lights.Children.Count == Math.Max(1, order.Count);
            for (int i = 0; same && i < order.Count; i++) same = rowsPanel.Children[i] == order[i].Text && lights.Children[i] == order[i].Light;
            if (same) return;
            rowsPanel.Children.Clear();
            lights.Children.Clear();
            foreach (Row row in order) { rowsPanel.Children.Add(row.Text); lights.Children.Add(row.Light); }
            if (order.Count == 0) lights.Children.Add(spare);
        }

        void ForgetRows()
        {
            rows.Clear();
            order.Clear();
            rowsPanel.Children.Clear();
            lights.Children.Clear();
            talker = hot = null;
        }

        Wave WaveOf(string name)
        {
            Wave wave;
            if (!waves.TryGetValue(name, out wave)) wave = waves[name] = new Wave();
            return wave;
        }

        // While the panel is away, the session that is talking (or was just shown) gets a bubble
        // next to its light with the sentence and the voice.
        void UpdateBubble(bool barShown)
        {
            Row found = null;
            bool talking = talkState.Length > 0, away = !IsOpen() && barShown && !dragging;
            if (away)
                foreach (Row row in order)
                {
                    if (row.TalkKind != null) { found = row; break; }  // what you are saying comes first
                    if (row.Saying && (found == null || row.Speaking || (!found.Speaking && row.FlashUntil > found.FlashUntil))) found = row;
                }
            bool orphan = away && talking && (found == null || found.TalkKind == null);  // push-to-talk with no session to show it on
            if (found == null && !orphan) { bubble.Goal = 0; return; }
            talker = orphan ? null : found;
            // The first line is always the session's name and title; push-to-talk shows as a sign
            // at its right and as words underneath.
            bool mine = orphan || found.TalkKind != null, listening = mine && talkState == "listening";
            string head = orphan ? TalkWords() : found.Name, sub = orphan ? "" : found.Title, body = orphan ? "" : mine ? TalkWords() : found.FlashText;
            string kind = mine ? TalkKind() : "";
            string shows = head + "\n" + sub + "\n" + body + "\n" + (orphan ? "" : found.State + found.Color) + listening + kind + Ui.SignInLight + Ui.TalkText;
            if (shows != bubbleShows)
            {
                bubbleShows = shows;
                Heading(bubbleLine1, head, sub, orphan ? "" : found.Color);
                bubbleBadge.Show(Ui.SignInLight && !orphan ? "" : kind);  // with no session there is no light to put it in
                bubbleLine2.Text = body;
                bubbleLine2.Visibility = body.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
                Brush ink = TalkInk();
                bool live = mine && (ink == Ui.MicInk || ink == Ui.LiveInk);
                if (live) Ui.GlintFor(body);
                bubbleLine2.Foreground = !mine ? Brushes.White : live ? Ui.MicLive : ink;
                bubbleLine2.FontWeight = mine && talkState == "listening" ? FontWeights.SemiBold : FontWeights.Normal;
                bubbleStrip.Wave = listening ? mic : orphan ? mic : found.Wave;
                bubbleStrip.Tint = mine ? Ui.Mic : Ui.Tint(found.State);
                bubbleStrip.NewestRight = corner.EndsWith("right");
            }
            if (bubble.Goal == 0) bubbleAt = Ui.Now;
            bubble.Goal = bubble.Natural();
        }

        // --- motion ---------------------------------------------------------------------------------

        // Frames are drawn in step with the screen, and only while something moves.
        void Run(bool on)
        {
            if (on == running) return;
            running = on;
            lastFrame = Ui.Now;
            if (on) CompositionTarget.Rendering += Frame; else CompositionTarget.Rendering -= Frame;
        }

        // One step of everything that moves: the panel and bubble unfolding, rows sliding in,
        // lights popping and spinning, the highlight under the mouse, and the voice wave.
        void Frame(object sender, EventArgs e)
        {
            // Showing or resizing a window makes WPF draw at once, which lands back here; without
            // this guard the steps pile up inside each other and the motion freezes for a moment.
            if (inFrame) return;
            inFrame = true;
            try { Step(); }
            finally { inFrame = false; }
        }

        void Step()
        {
            double now = Ui.Now, dt = Math.Min(0.05, now - lastFrame);
            lastFrame = now;
            frames++;
            bool again = false, expired = false, right = corner.EndsWith("right");
            if (dragging) { DragStep(); again = true; }
            if (talkState.Length > 0)
            {
                again = true;
                Ui.MoveMicInk(now);
                if (now >= talkUntil) { talkState = ""; expired = true; }
            }
            if (now < wheelUntil) again = true;
            else if (wheeling) { wheeling = false; expired = true; }  // the panel that came out for the wheel goes back
            again |= MoveSelector(dt);

            again |= panel.Step(dt, still);
            again |= bubble.Step(dt, still);
            if (panel.IsVisible)
            {
                // Each row slides out from the bar and fades in, a moment after the one above it.
                bool closing = panel.Goal == 0;
                sections.Opacity = closing ? Ui.Clamp(panel.Open * 1.6 - 0.3) : 1;
                for (int i = 0; i < order.Count; i++)
                {
                    double shown = still || closing ? 1 : Ui.EaseOut((now - openedAt - 0.03 * i) / 0.26);
                    order[i].Text.Opacity = shown;
                    order[i].Slide.X = (1 - shown) * (right ? 22 : -22);
                    if (shown < 1) again = true;
                }
            }
            if (bubble.IsVisible)
            {
                double shown = still || bubble.Goal == 0 ? bubble.Open : Ui.EaseOut((now - bubbleAt) / 0.3);
                bubbleWords.Opacity = shown;
                bubbleSlide.X = (1 - shown) * (right ? 18 : -18);
                if (shown < 1 && bubble.Goal > 0) again = true;
                bubbleStrip.InvalidateVisual();
                if (bubbleBadge.Moving) { bubbleBadge.InvalidateVisual(); again = true; }
            }
            foreach (Row row in order)
            {
                if (row.FlashText != null && !row.Speaking && now >= row.FlashUntil) { row.FlashText = null; row.Refresh(); expired = true; }
                bool moved = Ui.Approach(ref row.Orb.Hot, row == hot ? 1 : 0, 16, dt);
                row.Hot = row == hot ? 1 : 0;
                moved |= row.Glow(dt);
                if (moved || row.Orb.Moving)
                {
                    row.Orb.InvalidateVisual();
                    again = true;
                }
                if ((row.Speaking || row.Orb.Listening != null) && panel.IsVisible) row.Strip.InvalidateVisual();
                if (row.TalkKind != null && row.Badge.Moving) { row.Badge.InvalidateVisual(); again = true; }
                if (row.FlashText != null) again = true;  // so its end is noticed
            }
            if (expired) Render();
            if (!again && !expired) Run(false);
        }

        // The frame around the light in focus glides from one light to the next.
        bool MoveSelector(double dt)
        {
            double goal = 0, at = 3;
            bool found = false;
            foreach (Row row in order)
            {
                double room = Island ? Row.High : row.Light.Height;
                if (row.Focus) { goal = at + (room - selector.Height) / 2; found = true; break; }
                at += room;
            }
            if (found && selectorShown < 0.02) selectorY = goal;  // it appears in place instead of flying in
            bool moving = Ui.Approach(ref selectorShown, found ? 1 : 0, 12, dt);
            if (found && Math.Abs(goal - selectorY) > 0.05) { selectorY += (goal - selectorY) * (1 - Math.Exp(-20 * dt)); moving = true; }
            else if (found) selectorY = goal;
            selector.Opacity = selectorShown;
            selectorAt.X = Island ? selectorY : 0;
            selectorAt.Y = Island ? 0 : selectorY;
            return moving;
        }

        // What was said lately, shown in the panel while the cursor rests on it in list mode: the
        // lines of the session under the mouse (the author hovered another session and expected
        // its history, not the same lines as before). The session stays chosen while the mouse
        // moves on to the lines themselves. Before any row was touched it is the one in focus.
        // With `history: all` it is every session's lines, as it used to be.
        void BuildHistory()
        {
            historyLines.Children.Clear();
            string of = null;
            if (!historyAll)
            {
                foreach (Row row in order) if (row.Name == historyOf) of = row.Name;
                if (of == null) foreach (Row row in order) if (row.Focus) of = row.Name;
            }
            foreach (object o in history)
            {
                var h = (Dictionary<string, object>)o;
                if (of != null && Str(h, "name") != of) continue;
                if (historyLines.Children.Count >= (of != null ? 4 : 6)) break;
                var line = new TextBlock { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 2, 0, 2), FontSize = 12, MaxHeight = 34, TextTrimming = TextTrimming.CharacterEllipsis };
                line.Inlines.Add(new Run(Str(h, "ago") + "  ") { Foreground = Ui.Faint });
                line.Inlines.Add(new Run(Str(h, "name") + "  ") { FontWeight = FontWeights.SemiBold, Foreground = Ui.Named(Str(h, "color")) });
                line.Inlines.Add(new Run(Str(h, "text")) { Foreground = Ui.Dim });
                historyLines.Children.Add(line);
            }
        }

        // --- the mouse ------------------------------------------------------------------------------

        // The panel comes out when the mouse reaches the bar and goes shortly after it leaves. With
        // `hover: keys` the mouse only matters while the details are out for another reason.
        // While the mouse is on the bar, the bar takes the mouse so it can be dragged; the light
        // under it grows and its row is lit. In list mode, resting longer also shows the history.
        void WatchCursor()
        {
            CursorPoint cursor;
            if (peekForced || dragging || !rail.IsVisible || !GetCursorPos(out cursor)) return;
            int[] bar = rail.Area();
            bool onBar = Within(cursor, bar, 4);
            bool inside = onBar || (panel.IsVisible && panel.Goal > 0 && (Within(cursor, panel.Area(), 4) || Within(cursor, Between(bar, panel.Area()), 0)));
            if (inside) { insideTicks++; outsideTicks = 0; } else { outsideTicks++; insideTicks = 0; }
            bool wantHover = inside ? insideTicks >= 3 || hover : hover && outsideTicks < 9;  // 0.1 s to open, 0.3 s to close
            bool wantPeek = mode == "list" && (inside ? insideTicks >= 22 || peek : peek && outsideTicks < 9);
            if (!hoverOpens) wantHover = false;  // only the keys (or the list key) bring the details out
            Row under = null;
            // Nor does a light grow under a mouse that is only passing: nothing answers until the details are out.
            if (inside && rail.ActualHeight > 0 && (onBar || !Island) && (hoverOpens || IsOpen()))
            {
                // In the bar's own units, past its edge: along it, whichever way it runs. (In the
                // bar layout the rows are level with the lights, so this also works over the panel.)
                double along = Island ? (cursor.X - bar[0]) * rail.ActualWidth / Math.Max(1, bar[2]) - 4
                                      : (cursor.Y - bar[1]) * rail.ActualHeight / Math.Max(1, bar[3]) - 4;
                foreach (Row row in order)
                {
                    double room = Island ? Row.High : row.Light.Height;
                    if (along >= 0 && along < room) under = row;
                    along -= room;
                }
            }
            bool wantCatch = (moving || (onBar && (dragKeys.Length == 0 || Held(dragKeys)))) && Ui.Now > passUntil;
            if (wantCatch != catching) { catching = wantCatch; rail.CatchMouse(catching); Edge(); }
            if (under != hot)
            {
                hot = under;
                Run(true);
                if (hot != null && hot.Name != historyOf) { historyOf = hot.Name; if (peek && wantPeek) Render(); }
            }
            if (wantHover == hover && wantPeek == peek) return;
            hover = wantHover;
            peek = wantPeek;
            Render();
        }

        // --- the wheel ------------------------------------------------------------------------------

        // Ctrl+Alt and the mouse wheel move the focus from one session to the next, wherever
        // the mouse is. Windows only tells a program about the wheel through a mouse hook, and a
        // hook sits in the path of every mouse movement, so it is put in only while those keys
        // are down and there is more than one session to choose from.
        void WatchWheelKeys()
        {
            bool held = wheelKeys.Length > 0 && rail.IsVisible && Held(wheelKeys);
            // Holding those keys by themselves also brings the panel out. Not at once, so a quick
            // hotkey does not make it flicker, and not during push-to-talk, which has its bubble.
            if (!held) heldSince = 0;
            else if (heldSince == 0) heldSince = Ui.Now;
            bool open = held && talkState.Length == 0 && Ui.Now - heldSince >= 0.2;
            if (open != keysOpen) { keysOpen = open; Render(); }
            bool want = held && order.Count > 1;
            if (want && wheelHook == IntPtr.Zero) wheelHook = SetWindowsHookEx(WH_MOUSE_LL, wheelProc, GetModuleHandle(null), 0);
            else if (!want && wheelHook != IntPtr.Zero) { UnhookWindowsHookEx(wheelHook); wheelHook = IntPtr.Zero; wheelTurned = 0; }
        }

        bool Held(int[] keys)
        {
            foreach (int key in keys) if (!Pressed(key)) return false;
            // AltGr, used to type letters on many keyboards, reports itself as Ctrl+Alt: leave it alone.
            return (GetAsyncKeyState(VK_RMENU) & 0x8000) == 0;
        }

        // Called by Windows for every mouse event while the hook is in. The wheel is taken (the
        // app under the mouse does not scroll or zoom); everything else is passed on untouched.
        IntPtr OnMouse(int code, IntPtr wParam, IntPtr lParam)
        {
            if (code < 0 || wParam.ToInt32() != WM_MOUSEWHEEL || !Held(wheelKeys)) return CallNextHookEx(wheelHook, code, wParam, lParam);
            var data = (MouseHookData)Marshal.PtrToStructure(lParam, typeof(MouseHookData));
            int turned = (short)(data.Data >> 16);
            rail.Dispatcher.BeginInvoke(new Action(delegate { Wheel(turned); }));
            return new IntPtr(1);
        }

        // --- the held talk key ----------------------------------------------------------------------

        // A hotkey keeps a key from other programs only in part. Its press is kept, but over a
        // long hold a finger comes off Ctrl or Alt and the key then repeats into whatever has the
        // keyboard, and its release always gets through: Space paused the video the author was
        // watching, first while holding, and after that was mended, on letting go (a browser
        // acts on the release alone). So a keyboard hook takes the whole hold, press, repeats
        // and release, and the program in front never learns the key was touched.
        //
        // The release can only be kept if the press was (measured: Windows goes on thinking a
        // key is down when its release is kept from it, and never thinks it down when the press
        // was). The hook must therefore be in before the talk key goes down: it is put in as
        // soon as the hotkey's other keys (Ctrl, Alt) are down and stays for the hold. A talk
        // key pressed in the same instant as those keys still arrives as a plain hotkey; that
        // hold is handled as before, its repeats kept and its release passed on.
        // `keep_talk_key: always` keeps the hook in all the time, for a talk key without Ctrl
        // or Alt; `off` never uses it.
        void KeepKey(bool keep)
        {
            if (keep && keyHook == IntPtr.Zero) keyHook = SetWindowsHookEx(WH_KEYBOARD_LL, keyProc, GetModuleHandle(null), 0);
            else if (!keep && keyHook != IntPtr.Zero) { UnhookWindowsHookEx(keyHook); keyHook = IntPtr.Zero; }
        }

        void WatchTalkKeys()
        {
            // Talking is over and nothing has shown those keys to be held still: take Windows' word again.
            // Not while words that just went out can still be taken back: with the keys never let
            // go, Windows takes them for up, and Backspace would be a plain one for the program
            // in front. The hub's steps say how long that is; a quarter of a minute at most.
            bool unsent = (talkState == "transcribing" || talkState == "ready" || talkState == "sent" || talkState == "queued")
                && Ui.Now < talkUntil && Ui.Now < maskedUntil + 12;
            if (!holding && masked.Count > 0 && Ui.Now > maskedUntil && !unsent) masked.Clear();
            bool ahead = talkKey != 0 && (keepTalk == "always" || (keepTalk == "held" && talkMods != 0 && Mods(talkMods, false)));
            KeepKey(keepTalk != "off" && (holding || ahead || masked.Count > 0));
            // Should the release ever get past us, the repeats stopping says the key is up.
            if (holding && taken && repeated && Ui.Now - lastRepeat > 1.0) EndHold();
        }

        static bool Down(int key) { return (GetAsyncKeyState(key) & 0x8000) != 0; }

        // Is the key down, counting the ones we have hidden from Windows as down?
        bool Pressed(int key)
        {
            if (Down(key)) return true;
            if (key == VK_CONTROL) return masked.Contains(VK_LCONTROL) || masked.Contains(VK_RCONTROL);
            if (key == VK_MENU) return masked.Contains(VK_LMENU);
            if (key == VK_SHIFT) return masked.Contains(VK_LSHIFT) || masked.Contains(VK_RSHIFT);
            return masked.Contains(key);
        }

        // With Ctrl and Alt down, a click is a Ctrl+Alt+click to the program under the mouse, and
        // the author could not pause a video while talking: the player ignores such a click. So
        // when a hold begins, Windows is told that the talk hotkey's Ctrl, Alt and Shift have come
        // up, though they are still held. Clicks and the wheel are then plain ones, and we go on
        // counting those keys as down ourselves (Pressed) until their real release reaches the
        // hook, so the cancel key, another press of the talk key and the other hotkeys still work
        // without letting go first. Windows is only ever told "up", never "down", so a mistake
        // here cannot leave a key stuck for other programs; at worst they miss a shortcut until
        // the keys are pressed again. AltGr is left alone, and so is the Windows key, whose
        // release alone opens the Start menu.
        void MaskKeys()
        {
            if (!freeKeys || !holding || keyHook == IntPtr.Zero || Down(VK_RMENU)) return;
            var keys = new List<int>();
            if ((talkMods & MOD_ALT) != 0 && Down(VK_LMENU)) keys.Add(VK_LMENU);
            if ((talkMods & MOD_CONTROL) != 0 && Down(VK_LCONTROL)) keys.Add(VK_LCONTROL);
            if ((talkMods & MOD_CONTROL) != 0 && Down(VK_RCONTROL)) keys.Add(VK_RCONTROL);
            if ((talkMods & MOD_SHIFT) != 0 && Down(VK_LSHIFT)) keys.Add(VK_LSHIFT);
            if ((talkMods & MOD_SHIFT) != 0 && Down(VK_RSHIFT)) keys.Add(VK_RSHIFT);
            if (keys.Contains(VK_LMENU)) { Press(0xE8, false); Press(0xE8, true); }  // a key no keyboard has: Alt coming up after it opens no menu
            foreach (int key in keys) { masked.Add(key); Press(key, true); }
        }

        static void Press(int key, bool up)
        {
            keybd_event((byte)key, 0, (up ? 2u : 0u) | (key == VK_RCONTROL ? 1u : 0u), new UIntPtr((ulong)Ours));
        }

        // What a hotkey does when it arrives, from Windows or from the hook.
        // The hub knows two ways to move the focus, whichever arrows were used.
        static string Plain(string name) { return name == "focus_left" ? "focus_prev" : name == "focus_right" ? "focus_next" : name; }

        void Hotkey(string name)
        {
            name = Plain(name);
            if (name == "toggle") SetMode("toggle");
            if (name == "focus_prev" || name == "focus_next") ShowChoice();
            Send("hotkey", "name", name);
        }

        // The focus is being moved by hand: the panel comes out for a moment so the choice can be seen.
        void ShowChoice()
        {
            wheelUntil = Ui.Now + 1.6;
            wheeling = true;
            Render();
        }

        // Are the Ctrl, Alt, Shift and Win keys of a hotkey down? With `only`, and none of the others.
        bool Mods(uint wanted, bool only)
        {
            bool[] down = { Pressed(VK_CONTROL), Pressed(VK_MENU), Pressed(VK_SHIFT), Down(VK_LWIN) || Down(VK_RWIN) };
            uint[] flags = { MOD_CONTROL, MOD_ALT, MOD_SHIFT, MOD_WIN };
            for (int i = 0; i < 4; i++)
            {
                bool want = (wanted & flags[i]) != 0;
                if (want && !down[i]) return false;
                if (only && !want && down[i]) return false;
            }
            return true;
        }

        void EndHold()
        {
            if (!holding) return;
            holding = taken = false;
            holdTimer.Stop();
            maskedUntil = Ui.Now + MaskGrace;
            Send("hotkey", "name", "talk_end");
        }

        // Called by Windows for every key event while the hook is in. The key code is the first
        // number of what lParam points to.
        IntPtr OnKey(int code, IntPtr wParam, IntPtr lParam)
        {
            if (code < 0) return CallNextHookEx(keyHook, code, wParam, lParam);
            if (Marshal.ReadIntPtr(lParam, 16).ToInt64() == Ours) return CallNextHookEx(keyHook, code, wParam, lParam);  // sent by ourselves
            uint key = (uint)Marshal.ReadInt32(lParam);
            int message = wParam.ToInt32();
            bool down = message == WM_KEYDOWN || message == WM_SYSKEYDOWN;
            if (masked.Remove((int)key))  // really let go, or pressed anew: from here on Windows is right about this key again
                return CallNextHookEx(keyHook, code, wParam, lParam);
            // A keyboard repeats only the key pressed last. Once another key goes down during a
            // hold, the talk key stops repeating though it is still held, so its repeats can no
            // longer tell us anything (an arrow pressed to move the focus ended the recording
            // a second later). From then on only its release ends the hold.
            if (holding && down && key != heldKey) repeated = false;
            if (down && masked.Count > 0)  // Windows no longer sees our hotkeys' Ctrl and Alt, so they are matched here
                foreach (KeyValuePair<string, uint[]> claim in claims)
                    if (claim.Key != "talk" && claim.Value[0] == key && Mods(claim.Value[1], true))
                    {
                        string name = claim.Key;
                        maskedUntil = Ui.Now + MaskGrace;
                        rail.Dispatcher.BeginInvoke(new Action(delegate { Hotkey(name); }));
                        return new IntPtr(1);
                    }
            if (holding && key == heldKey)
            {
                if (down) { repeated = true; lastRepeat = Ui.Now; return new IntPtr(1); }  // the held key repeating
                if (!taken) return CallNextHookEx(keyHook, code, wParam, lParam);  // Windows saw this press, so it gets the release
                rail.Dispatcher.BeginInvoke(new Action(EndHold));
                return new IntPtr(1);
            }
            if (!holding && down && talkKey != 0 && key == talkKey && keepTalk != "off" && Mods(talkMods, true))
            {
                holding = taken = true;  // the hotkey, taken before Windows sees the key at all
                heldKey = key;
                repeated = false;
                rail.Dispatcher.BeginInvoke(new Action(delegate { Send("hotkey", "name", "talk"); MaskKeys(); }));
                return new IntPtr(1);
            }
            return CallNextHookEx(keyHook, code, wParam, lParam);
        }

        // One notch up is the session above, one notch down the session below. The panel comes
        // out for a moment so the choice can be seen.
        void Wheel(int turned)
        {
            if (order.Count < 2) return;
            wheelTurned += turned;
            while (Math.Abs(wheelTurned) >= 120)  // smooth wheels send a notch in small parts
            {
                Send("hotkey", "name", wheelTurned > 0 ? "focus_prev" : "focus_next");
                wheelTurned -= 120 * Math.Sign(wheelTurned);
            }
            wheelUntil = Ui.Now + 1.6;
            wheeling = true;
            Render();
        }

        // "Ctrl+Alt" -> the keys to watch. Empty turns the wheel off.
        static int[] Keys(string combo)
        {
            var keys = new List<int>();
            foreach (string raw in combo.Split('+'))
                switch (raw.Trim().ToLowerInvariant())
                {
                    case "ctrl": case "control": keys.Add(VK_CONTROL); break;
                    case "alt": keys.Add(VK_MENU); break;
                    case "shift": keys.Add(VK_SHIFT); break;
                    case "win": keys.Add(VK_LWIN); break;
                }
            return keys.ToArray();
        }

        static bool Within(CursorPoint p, int[] area, int slack)
        {
            return p.X >= area[0] - slack && p.X <= area[0] + area[2] + slack && p.Y >= area[1] - slack && p.Y <= area[1] + area[3] + slack;
        }

        // The strip between two pieces that sit side by side, so the mouse can cross it.
        static int[] Between(int[] a, int[] b)
        {
            int left = Math.Min(a[0] + a[2], b[0] + b[2]), right = Math.Max(a[0], b[0]);
            int top = Math.Min(a[1], b[1]), bottom = Math.Max(a[1] + a[3], b[1] + b[3]);
            return new[] { left, top, Math.Max(0, right - left), bottom - top };
        }

        // The left button went down on the bar: from now on it follows the mouse, frame by frame,
        // until the button comes up. The panel and bubble fold away while it travels.
        // `at` is where on the bar the button went down, as the press itself reported it. Asking
        // where the cursor is now is not the same: by the time the press is handled the mouse has
        // moved on, further the busier the overlay was, and the bar then followed the cursor from
        // beside it (the author: "sometimes the cursor is not aligned").
        void BeginDrag(Point at)
        {
            if (dragging) return;
            grabbedAt = rail.Area();
            Point held = HwndSource.FromHwnd(hwnd).CompositionTarget.TransformToDevice.Transform(at);
            grabX = (int)Math.Round(held.X);
            grabY = (int)Math.Round(held.Y);
            dragging = true;
            hover = peek = false;
            Edge();
            Render();
            panel.Step(0, true);
            bubble.Step(0, true);
        }

        void DragStep()
        {
            CursorPoint cursor;
            if (!GetCursorPos(out cursor)) return;
            int button = GetSystemMetrics(SM_SWAPBUTTON) != 0 ? VK_RBUTTON : VK_LBUTTON;
            if ((GetAsyncKeyState(button) & 0x8000) == 0) { EndDrag(); return; }
            Point to = HwndSource.FromHwnd(hwnd).CompositionTarget.TransformFromDevice.Transform(new Point(cursor.X - grabX, cursor.Y - grabY));
            rail.Left = to.X;
            rail.Top = to.Y;
        }

        // Dropped. If it did not really move, the press was a plain click, and that goes to
        // whatever is underneath the bar.
        void EndDrag()
        {
            dragging = false;
            int[] now = rail.Area();
            if (Math.Abs(now[0] - grabbedAt[0]) + Math.Abs(now[1] - grabbedAt[1]) > 3)
            {
                ReportMoved();
                if (moving) { moveTimer.Stop(); moveTimer.Interval = TimeSpan.FromSeconds(2); moveTimer.Start(); }
            }
            else if (!moving)
            {
                passUntil = Ui.Now + 0.4;
                catching = false;
                rail.CatchMouse(false);
                mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, UIntPtr.Zero);
                mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, UIntPtr.Zero);
            }
            insideTicks = outsideTicks = 0;
            Edge();
            Render();
            Place();
        }

        // The bar's edge shows what the mouse can do: brighter when it can be grabbed, amber while held.
        void Edge()
        {
            rail.Panel.BorderBrush = dragging || moving ? Ui.AmberEdge : catching ? Ui.BrightEdge : Ui.GlassEdge;
        }

        // "claude-speaks overlay move": the same dragging, announced, for when the bar is hard to find.
        void BeginMove()
        {
            moving = true;
            catching = true;
            rail.CatchMouse(true);
            Edge();
            bannerTimer.Stop();
            hasBanner = true;
            bannerTitle.Inlines.Clear();
            bannerTitle.Inlines.Add(new Run("Drag it to where you want it") { FontWeight = FontWeights.SemiBold });
            bannerHint.Text = "Any monitor \u00b7 You can drag it any time: just grab it with the mouse";
            bannerHint.Visibility = Visibility.Visible;
            moveTimer.Stop(); moveTimer.Interval = TimeSpan.FromSeconds(15); moveTimer.Start();
            Render();
        }

        void EndMove()
        {
            moveTimer.Stop();
            moving = false;
            hasBanner = false;
            Edge();
            Render();
            Place();
        }

        // Where the bar was dropped, as "which monitor, which corner, how far from it", so it keeps
        // its place when its size changes.
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
            if (Island)
            {
                // Where its middle is across the screen, and how far down. Near the middle it snaps to it.
                islandX = Ui.Clamp((rail.Left + rail.ActualWidth / 2 - work.Left) / Math.Max(1, work.Width));
                if (Math.Abs(islandX - 0.5) < 0.02) islandX = 0.5;
                islandY = Math.Max(0, rail.Top - work.Top);
                Write(new Dictionary<string, object> {
                    { "type", "moved" }, { "monitor", monitor }, { "island_x", Math.Round(islandX, 3) }, { "island_y", Math.Round(islandY) },
                });
                return;
            }
            string was = corner;
            double left = rail.Left, top = rail.Top, wide = rail.ActualWidth, tall = rail.ActualHeight;
            bool right = left + wide / 2 > work.Left + work.Width / 2, bottom = top + tall / 2 > work.Top + work.Height / 2;
            corner = (bottom ? "bottom" : "top") + "-" + (right ? "right" : "left");
            offsetX = Math.Max(0, right ? work.Right - (left + wide) : left - work.Left);
            offsetY = Math.Max(0, bottom ? work.Bottom - (top + tall) : top - work.Top);
            if (was != corner) { ForgetRows(); Stack(); }  // the panel changes sides, or its order
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

        // --- what the hub says ----------------------------------------------------------------------

        // A line about one session, shown for a few seconds (and for as long as it is being
        // spoken): in its row when the panel is out, in the bubble otherwise.
        void Flash(Dictionary<string, object> msg)
        {
            string name = Str(msg, "name"), text = Str(msg, "text");
            double until = Ui.Now + Num(msg, "seconds", 4);
            flashes[name] = new KeyValuePair<string, double>(text, until);
            Row row;
            if (rows.TryGetValue(name, out row)) { row.FlashText = text; row.FlashUntil = until; row.Refresh(); }
            Render();
        }

        void AddWave(Dictionary<string, object> msg) { AddLevels(WaveOf(Str(msg, "name")), msg); }

        void AddLevels(Wave wave, Dictionary<string, object> msg)
        {
            if (!msg.ContainsKey("levels")) return;
            var raw = (object[])msg["levels"];
            var levels = new double[raw.Length];
            for (int i = 0; i < raw.Length; i++) levels[i] = Convert.ToDouble(raw[i], CultureInfo.InvariantCulture);
            wave.Add(Ui.Now + Num(msg, "delay", 0), Math.Max(0.005, Num(msg, "step", 0.04)), levels);
            Run(true);
        }

        // Push-to-talk, step by step: listening (with your voice as a wave), transcribing, ready
        // (waiting for a go-ahead), sent, failed (text says why), focus (a tap moved the focus).
        // It shows on the session it is about, and moves with the focus.
        void Talk(Dictionary<string, object> msg)
        {
            string state = Str(msg, "state");
            if (state == "listening" && talkState != "listening") mic.Clear();
            talkState = state;
            talkName = Str(msg, "name");
            talkText = Str(msg, "text");
            talkHint = Str(msg, "hint");
            double seconds = Num(msg, "seconds", 0);
            talkUntil = seconds > 0 ? Ui.Now + seconds : double.MaxValue;
            Render();
        }

        // The sign for each step.
        string TalkKind()
        {
            switch (talkState)
            {
                case "listening": return "mic";
                case "transcribing": case "ready": return "dots";
                case "sent": case "queued": return "sent";
                case "failed": return "failed";
                default: return "";
            }
        }

        // The words under the session's name for each step.
        string TalkWords()
        {
            switch (talkState)
            {
                case "listening": return "Release to send";
                case "transcribing": return "Working out what you said\u2026";
                case "ready": return "\u201c" + talkText + "\u201d" + (talkHint.Length > 0 ? "\n" + talkHint : "");
                case "sent": return "\u201c" + talkText + "\u201d";
                case "queued": return "\u201c" + talkText + "\u201d\nIt gets this right after its current reply";
                case "focus": return "In focus";
                default: return talkText;  // failed: the text says what happened
            }
        }

        // How those words are written: your own words are white, and the overlay's words about
        // the step (what to do, what it is doing, what went wrong) are in the moving ink, with
        // what to do in bold.
        Brush TalkInk()
        {
            if (talkState == "listening") return Ui.MicInk;
            return talkState == "ready" || talkState == "sent" || talkState == "queued" ? Brushes.White : Ui.LiveInk;
        }

        // A permission prompt or question stays on screen until it is answered: the hotkeys act on it.
        void ShowRequest(Dictionary<string, object> msg)
        {
            hasRequest = msg.ContainsKey("text");
            if (hasRequest)
            {
                requestTitle.Inlines.Clear();
                requestTitle.Inlines.Add(new Run("\u25B2  ") { Foreground = Ui.AmberEdge, FontFamily = Ui.Symbols });
                requestTitle.Inlines.Add(new Run(Str(msg, "name") + "  ") { FontWeight = FontWeights.SemiBold, Foreground = Ui.Named(Str(msg, "color")) });
                requestTitle.Inlines.Add(new Run(Str(msg, "text")));
                object[] options = msg.ContainsKey("options") && msg["options"] != null ? (object[])msg["options"] : new object[0];
                string detail = Str(msg, "detail");
                requestDetail.Inlines.Clear();
                if (options.Length > 0)  // a question: each choice on a line of its own, behind its number
                {
                    requestDetail.FontFamily = requestTitle.FontFamily;
                    requestDetail.MaxHeight = 170;
                    for (int i = 0; i < options.Length; i++)
                    {
                        if (i > 0) requestDetail.Inlines.Add(new LineBreak());
                        requestDetail.Inlines.Add(new Run((i + 1) + "   ") { FontWeight = FontWeights.SemiBold, Foreground = Ui.AmberEdge });
                        requestDetail.Inlines.Add(new Run(Convert.ToString(options[i], CultureInfo.InvariantCulture)) { Foreground = Brushes.White });
                    }
                }
                else  // a permission prompt: the exact command or path
                {
                    requestDetail.FontFamily = requestMono;
                    requestDetail.MaxHeight = 70;  // about four lines; the terminal has the full command
                    requestDetail.Text = detail;
                }
                requestDetail.Visibility = options.Length > 0 || detail.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
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

        // The lights are solid while something is happening or the mouse is on them, a little
        // fainter at rest.
        void Fade()
        {
            bool busy = hasRequest || hasBanner || moving || hover || peek;
            foreach (Row row in order) busy = busy || row.Showing;
            double target = opaque || busy ? 1.0 : (mode == "list" ? listOpacity : idleOpacity);
            if (target == lastFade) return;
            lastFade = target;
            lights.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(target, TimeSpan.FromMilliseconds(220)));
        }

        // --- where things go ------------------------------------------------------------------------

        void Place()
        {
            if (dragging) return;
            Rect work = WorkArea();
            bool right = corner.EndsWith("right"), bottom = corner.StartsWith("bottom");
            if (Island)
            {
                // Its middle stays where it was put (the top middle of the screen unless dragged),
                // however many lights it holds.
                double wide = rail.ActualWidth, tall = rail.ActualHeight;
                rail.Left = Math.Max(work.Left, Math.Min(work.Right - wide, work.Left + work.Width * islandX - wide / 2));
                rail.Top = Math.Max(work.Top, Math.Min(work.Bottom - tall, work.Top + islandY));
                bool low = rail.Top + tall / 2 > work.Top + work.Height / 2;
                if (low != islandLow) { islandLow = low; Stack(); }
            }
            else
            {
                rail.Left = right ? work.Right - rail.ActualWidth - offsetX : work.Left + offsetX;
                rail.Top = bottom ? work.Bottom - rail.ActualHeight - offsetY : work.Top + offsetY;
            }
            PlaceSides();
        }

        // Bar: the panel and the bubble sit beside it, on the side with more room, the panel level
        // with the bar and the bubble level with the light of the session that is talking.
        // Island: both drop down from the middle of it. Their top left corners are set once per
        // opening and stay there while they unfold.
        void PlaceSides()
        {
            if (!rail.IsVisible) return;
            Rect work = WorkArea();
            bool right = corner.EndsWith("right"), bottom = Low;
            double width = rail.ActualWidth > 0 ? rail.ActualWidth : Row.High + 8, height = rail.ActualHeight;
            if (Island)
            {
                double middle = rail.Left + width / 2;
                // Under its middle (over it in the lower half of the screen), kept on the screen.
                if (panel.Goal > 0)
                {
                    panel.Left = Math.Max(work.Left + 4, Math.Min(work.Right - PanelWidth - 4, middle - PanelWidth / 2));
                    panel.Top = bottom ? rail.Top - Gap - panel.Goal : rail.Top + height + Gap;
                }
                if (bubble.Goal > 0)
                {
                    bubble.Left = Math.Max(work.Left + 4, Math.Min(work.Right - BubbleWidth - 4, middle - BubbleWidth / 2));
                    bubble.Top = bottom ? rail.Top - Gap - bubble.Goal : rail.Top + height + Gap;
                }
                return;
            }
            if (panel.Goal > 0)
            {
                panel.Left = right ? rail.Left - PanelWidth - Gap : rail.Left + width + Gap;
                double top = bottom ? rail.Top + height - panel.Goal : rail.Top;
                panel.Top = Math.Max(work.Top + 4, Math.Min(work.Bottom - panel.Goal - 4, top));
            }
            if (bubble.Goal > 0)
            {
                double level = height / 2;
                try { if (talker != null) level = talker.Light.TransformToAncestor(rail).Transform(new Point(0, talker.Light.ActualHeight / 2)).Y; }
                catch (InvalidOperationException) { }  // its light is not on screen yet
                bubble.Left = right ? rail.Left - BubbleWidth - Gap : rail.Left + width + Gap;
                bubble.Top = Math.Max(work.Top + 4, Math.Min(work.Bottom - bubble.Goal - 4, rail.Top + level - bubble.Goal / 2));
            }
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
            claims.Clear();
            talkKey = talkMods = 0;
            int next = 1;
            foreach (KeyValuePair<string, string> entry in wantedKeys)
            {
                bool answers = entry.Key == "allow" || entry.Key == "deny" || entry.Key == "cancel" || entry.Key.StartsWith("option") || entry.Key.StartsWith("focus_");
                // The focus moves with the arrows that point the way the lights run: up and down
                // for the bar, left and right for the island. The other pair is left to other programs.
                bool sideways = entry.Key == "focus_left" || entry.Key == "focus_right";
                if (sideways != Island && entry.Key.StartsWith("focus_")) continue;
                if (answers && !liveKeys.Contains(Plain(entry.Key))) continue;
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
                if (RegisterHotKey(hwnd, next, modifiers, vk))
                {
                    hotkeys[next] = entry.Key; hotkeyKeys[next] = vk; next++;
                    claims[entry.Key] = new uint[] { vk, modifiers & ~MOD_NOREPEAT };
                    if (entry.Key == "talk") { talkKey = vk; talkMods = modifiers & ~MOD_NOREPEAT; }
                }
                else if (complained.Add(combo)) Error("hotkey " + combo + " is already taken by another program");
            }
        }

        IntPtr WndProc(IntPtr window, int message, IntPtr wParam, IntPtr lParam, ref bool handled)
        {
            string name;
            if (message == WM_HOTKEY && hotkeys.TryGetValue(wParam.ToInt32(), out name))
            {
                if (name == "talk")
                {
                    // This press got past the hook (pressed in one go with Ctrl and Alt, or the hook
                    // is off): Windows has seen it, so its release is watched for and passed on.
                    if (holding) { handled = true; return IntPtr.Zero; }
                    heldKey = hotkeyKeys[wParam.ToInt32()];
                    holding = true; taken = false; repeated = false;
                    holdTimer.Start();
                    KeepKey(keepTalk != "off");
                    Send("hotkey", "name", name);
                    MaskKeys();
                }
                else Hotkey(name);
                handled = true;
            }
            return IntPtr.Zero;
        }

        // --- output to the hub ------------------------------------------------------------------

        // Where the pieces are on screen, so a check can take a picture of exactly those.
        void ReportBounds()
        {
            rail.UpdateLayout();
            var pieces = new List<object>();
            if (rail.IsVisible) pieces.Add(rail.Area());
            var reply = new Dictionary<string, object> { { "type", "bounds" }, { "visible", rail.IsVisible } };
            if (rail.IsVisible)
            {
                if (panel.IsVisible) pieces.Add(panel.Area());
                if (bubble.IsVisible) pieces.Add(bubble.Area());
                int[] area = rail.Area();
                reply["x"] = area[0]; reply["y"] = area[1]; reply["w"] = area[2]; reply["h"] = area[3];
                reply["pieces"] = pieces;
                reply["layout"] = layout;
                reply["open"] = IsOpen();
                reply["opacity"] = lights.Opacity;
                reply["monitor"] = monitor;
                reply["catches_mouse"] = catching;
                reply["moving"] = running;
                reply["clock"] = Math.Round(Ui.Now, 3);  // with "frames": how many pictures a second it draws
                reply["frames"] = frames;
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
