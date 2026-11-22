// The sidetone overlay: a glass bar with one status light per Claude session. Under the
// mouse a panel unfolds beside it with names and titles, and a speech bubble with a voice wave
// appears while a session talks. The bar can be dragged with the mouse. It only draws what the
// hub tells it to and reports hotkeys.
// Protocol: one JSON object per line.
// In on stdin: config, state, flash, wave, request, banner, keys, mode, move, peek, settings, hold_key, bounds, quit.
// Out on stdout: ready, hotkey, mode, moved, setting, settings, bounds, error.
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
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace ClaudeSpeaks
{
    static class Ui
    {
        static readonly Stopwatch watch = Stopwatch.StartNew();
        public static double Now { get { return watch.Elapsed.TotalSeconds; } }

        public static readonly FontFamily Symbols = new FontFamily("Segoe UI Symbol");
        public static readonly Color Amber = Color.FromRgb(0xFF, 0xB3, 0x00);
        // The microphone's color: the light, bars and wave of the session you are talking to.
        // The tool's blue since the author asked for "the hex code to be the brand color"
        // (`mic_color`; it was a pink, "#FF6E8A", chosen to stand apart from the lights' own
        // colors, of which the blue of "working" is the nearest to this one).
        public static Color Mic = Color.FromRgb(0x00, 0x68, 0x96);
        // The same color for what is drawn thin on the dark glass (the wave of your voice, a
        // sign beside a name): a dark color is lifted toward white there, or it cannot be seen.
        // The blue itself is 2.7 to 1 against the glass; lifted by two fifths it is about 6 to 1.
        public static Color MicLine
        {
            get
            {
                double light = (0.2126 * Mic.R + 0.7152 * Mic.G + 0.0722 * Mic.B) / 255;
                return light < 0.45 ? Mix(Mic, Colors.White, 0.4) : Mic;
            }
        }
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

        // The mark on a light whose session has words of yours waiting: the red of a notification,
        // or a color of your own (waiting_color, "#RRGGBB").
        public static Color Waiting = Color.FromRgb(0xFF, 0x3B, 0x30);
        public static string WaitingMark = "number";  // or "clock", "dot"
        // How see-through the glass is, 0 to 100 (`glass_clear`): 0 plain dark glass with no blur,
        // 50 the look it always had (a tint of 55 to 65 % over the blur), 100 the clearest (20 to
        // 30 %). The author, 2026-11-21, of Blur and Plain: "both are glass-like ... percentage like
        // from 0 to 100?".
        public static double GlassClear = 50;
        public static string WaitingMany = "face";  // above nine messages: a dismayed face | "number" = "9+"
        // Which messages show their number across the whole light before it goes to the corner:
        // never (it comes up in its corner, with a small jump) | first = the first to wait | each.
        public static string WaitingCover = "never";
        public static double WaitingSize = 9.2;  // the radius of the number's disc (and the face's) in its corner
        public static double WaitingHold = 0.9;  // seconds the number covers the whole light before it goes to the corner

        // The arc around a light: how full that session's context is. From ContextWarn percent
        // on it is drawn in the second color (0 = never).
        public static double ContextWarn = 80;
        public static Color Context = Colors.White, ContextFull = Color.FromRgb(0xFF, 0x8A, 0x3D);

        public static Color ColorOr(string hex, Color otherwise)
        {
            try { if (hex != null && hex.Length > 0) return (Color)ColorConverter.ConvertFromString(hex); }
            catch (Exception) { }  // not a color: as it was
            return otherwise;
        }

        public static void SetWaitingColor(string hex)
        {
            try { if (hex != null && hex.Length > 0) Waiting = (Color)ColorConverter.ConvertFromString(hex); }
            catch (Exception) { }  // not a color: as it was
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
            double c = Clamp(GlassClear / 100);
            double top = c <= 0.5 ? 0xEB + (0x8C - 0xEB) * c * 2 : 0x8C + (0x33 - 0x8C) * (c - 0.5) * 2;
            double bottom = c <= 0.5 ? 0xEB + (0xA6 - 0xEB) * c * 2 : 0xA6 + (0x4D - 0xA6) * (c - 0.5) * 2;
            return Gradient(new Point(0, 0), new Point(0, 1), "#" + ((int)Math.Round(top)).ToString("X2") + "3A4150",
                            "#" + ((int)Math.Round(bottom)).ToString("X2") + "12151B");
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
        public int Waiting;  // how many messages of yours are held for this session until it can take them
        public double WaitingSince = -10;  // when the last of them joined
        public bool Covers = true;  // that one shows itself across the whole light before it goes to the corner
        public Wave Wave, Listening;  // Listening: your own voice, while you hold the talk key for this session
        public double Born = Ui.Now, Changed = -10, Hot, SignSince;
        public double Context = -1;  // how full its context is, in percent; below 0 = not known or not shown
        double contextFrom, contextSince = -10;
        const double GaugeAt = 16.5, GaugeGrows = 0.6;  // the arc's radius, and the seconds it takes to reach a new figure

        public void SetContext(double percent)
        {
            if (Math.Abs(percent - Context) < 0.05) return;
            contextFrom = Math.Max(0, ContextNow(Ui.Now));  // from where the arc is right now
            contextSince = Ui.Now;
            Context = percent;
        }

        double ContextNow(double t)
        {
            double k = Ui.Motionless ? 1 : Ui.EaseOut((t - contextSince) / GaugeGrows);
            return contextFrom + (Context - contextFrom) * k;
        }

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
                if (Signed && (Sign == "dots" || Sign == "wait" || t - SignSince < 0.5)) return true;
                if (Waiting > 0 && (Ui.WaitingMark != "number" || t - WaitingSince < Ui.WaitingHold + MarkMove + 0.1)) return true;
                if (Context >= 0 && t - contextSince < GaugeGrows + 0.1) return true;
                return Speaking || Listening != null || State == "working" || State == "needs_you" || t - Changed < 0.8 || t - Born < 0.45;
            }
        }

        protected override void OnRender(DrawingContext dc)
        {
            double t = Ui.Now, age = t - Changed;
            var c = new Point(Size / 2, Size / 2);
            bool signed = Signed;
            Color tint = signed ? (Sign == "sent" ? Ui.Tint("done") : Sign == "failed" || Sign == "stop" ? Ui.Tint("failed") : Ui.Mic) : Listening != null ? Ui.Mic : Ui.Tint(State);
            Wave wave = Listening ?? Wave;
            double bump = age < 0.4 ? 0.2 * Math.Sin(Math.PI * age / 0.4) : 0;
            double scale = Ui.Overshoot((t - Born) / 0.4) * (1 + bump + 0.14 * Hot);
            dc.PushTransform(new ScaleTransform(scale, scale, c.X, c.Y));
            Gauge(dc, c, t);
            if (age < 0.8 && Listening == null && (signed || (!Speaking && State != "idle" && State != "working")))
            {
                double ring = Ui.EaseOut(age / 0.8);  // a ring that spreads and fades
                dc.DrawEllipse(null, Ui.Line(tint, 0.7 * (1 - ring), 2), c, 13 + 9 * ring, 13 + 9 * ring);
            }
            if (signed)
            {
                dc.DrawEllipse(Ui.Alpha(tint, 0.30), Ui.Line(tint, 0.95, 1.5), c, 13, 13);
                Badge.Draw(dc, Sign, c.X, c.Y, t, t - SignSince, true);
                if (Sign != "wait") Mark(dc, c, t);  // the clock says it already
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
                Mark(dc, c, t);
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
            Mark(dc, c, t);
            dc.Pop();
        }

        // How full the session's context is: a thin arc just outside the light that fills
        // clockwise from the top, over a faint ring that shows where full would be.
        void Gauge(DrawingContext dc, Point c, double t)
        {
            if (Context < 0) return;
            double share = Ui.Clamp(ContextNow(t) / 100);
            Color ink = Ui.ContextWarn > 0 && Context >= Ui.ContextWarn ? Ui.ContextFull : Ui.Context;
            dc.DrawEllipse(null, Ui.Line(Colors.White, 0.12, 2), c, GaugeAt, GaugeAt);
            if (share >= 0.995) { dc.DrawEllipse(null, Ui.Line(ink, 0.85, 2), c, GaugeAt, GaugeAt); return; }
            double a = -Math.PI / 2, b = a + 2 * Math.PI * Math.Max(share, 0.004);
            var arc = new StreamGeometry();
            using (StreamGeometryContext g = arc.Open())
            {
                g.BeginFigure(new Point(c.X + GaugeAt * Math.Cos(a), c.Y + GaugeAt * Math.Sin(a)), false, false);
                g.ArcTo(new Point(c.X + GaugeAt * Math.Cos(b), c.Y + GaugeAt * Math.Sin(b)), new Size(GaugeAt, GaugeAt), 0, share > 0.5, SweepDirection.Clockwise, true, false);
            }
            dc.DrawGeometry(null, Ui.Line(ink, 0.85, 2), arc);
        }

        // Words are waiting for this session. By default (waiting_mark "number") the number of
        // messages, white on red: it first covers the whole light, as the words are taken in,
        // then shrinks and glides to the upper right, where it stays for as long as they wait;
        // it does that again each time another message joins. "clock" is a small clock whose
        // hand goes round (with the number from two on), "dot" a plain breathing dot.
        void Mark(DrawingContext dc, Point c, double t)
        {
            if (Waiting <= 0) return;
            var corner = new Point(c.X + 10.5, c.Y - 10.5);
            string count = Waiting > 9 ? "9+" : Waiting.ToString(CultureInfo.InvariantCulture);
            if (Ui.WaitingMark == "number")
            {
                // Whole light for a moment, then on its way to the corner; or, for a message that
                // joins others, a small jump where it is.
                double age = t - WaitingSince, k = Ui.Motionless || !Covers ? 1 : Ui.Clamp((age - Ui.WaitingHold) / MarkMove);
                k = k * k * (3 - 2 * k);  // leaves and lands softly
                double pop = Ui.Motionless ? 1 : Covers ? Ui.Overshoot(age / 0.3) : 1 + (age < 0.4 ? 0.4 * Math.Sin(Math.PI * age / 0.4) : 0);
                var at = new Point(c.X + (corner.X - c.X) * k, c.Y + (corner.Y - c.Y) * k);
                // In its corner the disc is as large as a face needs to be read (waiting_size),
                // and the number's disc is the same size; it sits a little further in for it.
                double r = (13.5 + (Ui.WaitingSize - 13.5) * k) * pop, inward = Math.Max(0, Ui.WaitingSize - 7.7) * k;
                at = new Point(at.X - inward, at.Y + inward);
                if (Waiting > 9 && Ui.WaitingMany == "face") { Dismayed(dc, at, r); return; }
                dc.DrawEllipse(Ui.Alpha(Ui.Waiting, 0.97), null, at, r, r);
                Number(dc, count, at, (count.Length > 1 ? 0.95 : 1.25) * r);
                return;
            }
            Brush rim = Ui.Alpha(Color.FromRgb(0x14, 0x14, 0x18), 0.9);
            if (Ui.WaitingMark == "dot")
            {
                double breath = 0.5 + 0.5 * Math.Sin(t * 3.2);
                dc.DrawEllipse(Ui.Alpha(Ui.Waiting, 0.22 * breath), null, corner, 5.2 + 2 * breath, 5.2 + 2 * breath);
                dc.DrawEllipse(rim, null, corner, 5.2, 5.2);
                dc.DrawEllipse(Ui.Alpha(Ui.Waiting, 0.85 + 0.15 * breath), null, corner, 3.8, 3.8);
                return;
            }
            if (Waiting > 9)  // two signs do not fit the small clock: the face as with the number, or a disc with room for "9+"
            {
                double big = Math.Max(Ui.WaitingSize, 8.4), inward = big - 6.4;
                var at = new Point(corner.X - inward, corner.Y + inward);
                if (Ui.WaitingMany == "face") { Dismayed(dc, at, big); return; }
                dc.DrawEllipse(rim, null, at, big + 1.6, big + 1.6);
                dc.DrawEllipse(Ui.Alpha(Ui.Waiting, 0.95), Ui.Line(Colors.White, 0.9, 1.1), at, big, big);
                Number(dc, count, at, 0.95 * big);
                return;
            }
            dc.DrawEllipse(rim, null, corner, 8, 8);
            dc.DrawEllipse(Ui.Alpha(Ui.Waiting, 0.95), Ui.Line(Colors.White, 0.9, 1.1), corner, 6.4, 6.4);
            if (Waiting > 1)
            {
                Number(dc, count, corner, 9.5);
                return;
            }
            double turn = t * 1.8;
            Pen hand = Ui.Line(Colors.White, 1, 1.3);
            dc.DrawLine(hand, corner, new Point(corner.X, corner.Y - 4));
            dc.DrawLine(hand, corner, new Point(corner.X + 3 * Math.Sin(turn), corner.Y - 3 * Math.Cos(turn)));
        }

        const double MarkMove = 0.55;  // seconds the number takes from the middle of the light to its corner
        static readonly Typeface MarkFace = new Typeface(new FontFamily("Segoe UI"), FontStyles.Normal, FontWeights.Bold, FontStretches.Normal);

        // More than nine messages: a dismayed face in the yellow of a smiley, after a picture
        // the author gave as the look to go for: brows raised in the middle, oval eyes with a
        // line under each, and a wavy mouth turned down ("so many, what are you doing?").
        // Before it: "9+", a tight fit in so small a circle; a shocked face in white on red,
        // which looked frightening; a grinning one, which looked unwell; an unimpressed one.
        static readonly Brush FaceSkin = Ui.Alpha(Color.FromRgb(0xFF, 0xCE, 0x4A), 1), FaceInk = Ui.Alpha(Color.FromRgb(0x5E, 0x40, 0x0A), 1);

        static void Dismayed(DrawingContext dc, Point at, double r)
        {
            dc.DrawEllipse(FaceSkin, null, at, r, r);
            var thick = new Pen(FaceInk, Math.Max(1.1, 0.12 * r)) { StartLineCap = PenLineCap.Round, EndLineCap = PenLineCap.Round, LineJoin = PenLineJoin.Round };
            var thin = new Pen(FaceInk, Math.Max(0.9, 0.08 * r)) { StartLineCap = PenLineCap.Round, EndLineCap = PenLineCap.Round };
            var lines = new StreamGeometry();
            using (StreamGeometryContext g = lines.Open())
            {
                // Brows: from the outside in, rising to a small hook over the nose.
                g.BeginFigure(P(at, r, -0.70, -0.28), false, false);
                g.QuadraticBezierTo(P(at, r, -0.34, -0.30), P(at, r, -0.24, -0.52), true, true);
                g.BeginFigure(P(at, r, 0.66, -0.28), false, false);
                g.QuadraticBezierTo(P(at, r, 0.28, -0.30), P(at, r, 0.18, -0.54), true, true);
                // The mouth: up from the left, a dip, and down again on the right.
                g.BeginFigure(P(at, r, -0.36, 0.66), false, false);
                g.QuadraticBezierTo(P(at, r, -0.26, 0.44), P(at, r, -0.04, 0.47), true, true);
                g.QuadraticBezierTo(P(at, r, 0.14, 0.50), P(at, r, 0.22, 0.42), true, true);
                g.QuadraticBezierTo(P(at, r, 0.38, 0.36), P(at, r, 0.42, 0.60), true, true);
            }
            dc.DrawGeometry(null, thick, lines);
            dc.DrawEllipse(FaceInk, null, P(at, r, -0.36, -0.06), 0.13 * r, 0.17 * r);
            dc.DrawEllipse(FaceInk, null, P(at, r, 0.36, -0.06), 0.13 * r, 0.17 * r);
            dc.DrawLine(thin, P(at, r, -0.46, 0.14), P(at, r, -0.24, 0.10));  // the lines under the eyes
            dc.DrawLine(thin, P(at, r, 0.22, 0.10), P(at, r, 0.52, 0.09));
        }

        static Point P(Point at, double r, double x, double y) { return new Point(at.X + x * r, at.Y + y * r); }

        static void Number(DrawingContext dc, string text, Point at, double size)
        {
            var drawn = new FormattedText(text, CultureInfo.InvariantCulture, FlowDirection.LeftToRight, MarkFace, Math.Max(1, size), Brushes.White);
            // The middle of the strokes themselves goes on the middle of the disc. The line a
            // digit stands in has room below for letters that hang down, so set by its line
            // a digit sits low (half a pixel to a pixel here, measured in pictures).
            Geometry ink = drawn.BuildGeometry(new Point(0, 0));
            Rect box = ink.Bounds;
            if (box.IsEmpty) return;
            dc.PushTransform(new TranslateTransform(at.X - (box.X + box.Width / 2), at.Y - (box.Y + box.Height / 2)));
            dc.DrawGeometry(Brushes.White, null, ink);
            dc.Pop();
        }
    }

    // The box in front of a choice that can be ticked. Drawn as one shape, not taken from a font
    // (whose ticked and unticked boxes differ in size, so the words beside them moved) and not
    // made of a border around a filling (a seam shows between the two): unticked it is an
    // outline, ticked it is one filled square with the tick in its middle.
    // The small sign in front of a line of the history: how the turn it closed had ended. A
    // check for done, a cross for failed, "!" for something asked of you, a ring for a word
    // on the way, a small speech bubble for an answer on the side.
    class EndMark : FrameworkElement
    {
        readonly string kind;
        readonly bool missed;  // never heard to its end: a white dot at the mark's upper right

        public EndMark(string kind, bool missed)
        {
            this.kind = kind;
            this.missed = missed;
            Width = 14; Height = 16; Margin = new Thickness(0, 0, 5, 0);
            VerticalAlignment = VerticalAlignment.Top;
            IsHitTestVisible = false;
        }

        protected override void OnRender(DrawingContext dc)
        {
            switch (kind)
            {
                case "done":
                {
                    Pen pen = Ui.Line(Ui.Tint("done"), 1, 1.7);
                    dc.DrawLine(pen, new Point(2.5, 8.6), new Point(5.1, 11.2));
                    dc.DrawLine(pen, new Point(5.1, 11.2), new Point(10.4, 5.4));
                    break;
                }
                case "failed":
                {
                    Pen pen = Ui.Line(Ui.Tint("failed"), 1, 1.7);
                    dc.DrawLine(pen, new Point(3.4, 5.4), new Point(9.4, 11.4));
                    dc.DrawLine(pen, new Point(9.4, 5.4), new Point(3.4, 11.4));
                    break;
                }
                case "needs_you":
                    dc.DrawLine(Ui.Line(Ui.Amber, 1, 1.8), new Point(6.4, 4.6), new Point(6.4, 9.2));
                    dc.DrawEllipse(Ui.Alpha(Ui.Amber, 1), null, new Point(6.4, 12.2), 1.1, 1.1);
                    break;
                case "progress":
                    dc.DrawEllipse(null, Ui.Line(Ui.Tint("working"), 1, 1.5), new Point(6.4, 8.4), 3.1, 3.1);
                    break;
                case "aside":
                {
                    Pen pen = Ui.Line(Colors.White, 0.7, 1.3);
                    dc.DrawRoundedRectangle(null, pen, new Rect(2.2, 4.4, 8.6, 6.2), 2, 2);
                    dc.DrawLine(pen, new Point(4.6, 10.6), new Point(3.6, 12.8));
                    break;
                }
                default:
                    dc.DrawEllipse(Ui.Alpha(Colors.White, 0.45), null, new Point(6.4, 8.4), 1.6, 1.6);
                    break;
            }
            if (missed) dc.DrawEllipse(Brushes.White, new Pen(Ui.Alpha(Color.FromRgb(0x20, 0x24, 0x2C), 1), 1.2), new Point(11.2, 3.6), 2.7, 2.7);
        }
    }

    class TickMark : FrameworkElement
    {
        const double Side = 14;
        readonly bool on;

        public TickMark(bool on)
        {
            this.on = on;
            Width = Height = Side;
            Margin = new Thickness(0, 2, 0, 2);
            IsHitTestVisible = false;
        }

        protected override void OnRender(DrawingContext dc)
        {
            if (!on)
            {
                dc.DrawRoundedRectangle(null, new Pen(Ui.AmberEdge, 1.5), new Rect(0.75, 0.75, Side - 1.5, Side - 1.5), 3, 3);
                return;
            }
            dc.DrawRoundedRectangle(Ui.AmberEdge, null, new Rect(0, 0, Side, Side), 3.5, 3.5);
            // The tick's own box is 6.8 by 5 and sits in the middle of the square.
            var pen = new Pen(new SolidColorBrush(Color.FromRgb(0x14, 0x14, 0x18)), 1.9) { StartLineCap = PenLineCap.Round, EndLineCap = PenLineCap.Round, LineJoin = PenLineJoin.Round };
            var tick = new StreamGeometry();
            using (StreamGeometryContext g = tick.Open())
            {
                g.BeginFigure(new Point(3.6, 7.1), false, false);
                g.LineTo(new Point(6.0, 9.5), true, true);
                g.LineTo(new Point(10.4, 4.5), true, true);
            }
            dc.DrawGeometry(null, pen, tick);
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
    // A speaker with a slash across it: the voice is off. Drawn, not taken from a font: the
    // font's struck-out speaker has a small cross at its side that cannot be made out at the
    // size of a line (the author: "it's not very clear ... very small"; they wanted a slash
    // over it). Drawn in a box of `Side`, the slash cut out of the speaker by a gap.
    class MutedSpeaker : FrameworkElement
    {
        public double Side = 16;
        public Brush Ink = Ui.Dim;
        public bool Struck = true;  // false: the same speaker sounding, for "Voice is on"

        public MutedSpeaker(double size)
        {
            Side = size;
            Width = Height = size;
            IsHitTestVisible = false;
        }

        protected override void OnRender(DrawingContext dc)
        {
            double k = Side / 16.0;
            var speaker = new StreamGeometry();
            using (StreamGeometryContext g = speaker.Open())
            {
                g.BeginFigure(new Point(1.5 * k, 5.6 * k), true, true);
                g.LineTo(new Point(4.6 * k, 5.6 * k), true, false);
                g.LineTo(new Point(8.6 * k, 2.0 * k), true, false);
                g.LineTo(new Point(8.6 * k, 14.0 * k), true, false);
                g.LineTo(new Point(4.6 * k, 10.4 * k), true, false);
                g.LineTo(new Point(1.5 * k, 10.4 * k), true, false);
            }
            var wave = new StreamGeometry();
            using (StreamGeometryContext g = wave.Open())
            {
                g.BeginFigure(new Point(10.9 * k, 5.4 * k), false, false);
                g.ArcTo(new Point(10.9 * k, 10.6 * k), new Size(3.4 * k, 3.4 * k), 0, false, SweepDirection.Clockwise, true, false);
                g.BeginFigure(new Point(12.6 * k, 3.2 * k), false, false);
                g.ArcTo(new Point(12.6 * k, 12.8 * k), new Size(5.6 * k, 5.6 * k), 0, false, SweepDirection.Clockwise, true, false);
            }
            var line = new Pen(Ink, 1.3 * k) { StartLineCap = PenLineCap.Round, EndLineCap = PenLineCap.Round };
            if (!Struck)
            {
                dc.DrawGeometry(Ink, null, speaker);
                dc.DrawGeometry(null, line, wave);
                return;
            }
            // Everything but a band along the slash, so the slash stands apart from what it crosses.
            var band = new LineGeometry(new Point(1.2 * k, 1.2 * k), new Point(14.8 * k, 14.8 * k)).GetWidenedPathGeometry(new Pen(Brushes.Black, 3.6 * k));
            var keep = new CombinedGeometry(GeometryCombineMode.Exclude, new RectangleGeometry(new Rect(-2 * k, -2 * k, 20 * k, 20 * k)), band);
            dc.PushClip(keep);
            dc.DrawGeometry(Ink, null, speaker);
            dc.DrawGeometry(null, line, wave);
            dc.Pop();
            dc.DrawLine(new Pen(Ink, 1.5 * k) { StartLineCap = PenLineCap.Round, EndLineCap = PenLineCap.Round },
                        new Point(1.8 * k, 1.8 * k), new Point(14.2 * k, 14.2 * k));
        }
    }

    class Badge : FrameworkElement
    {
        public string Kind = "";  // "", mic, dots, sent, wait, failed, stop
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
        public bool Moving { get { return Kind == "mic" || Kind == "dots" || Kind == "wait" || (Kind.Length > 0 && !settled); } }

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
                    Microphone(dc, cx, cy, Ui.Alpha(inLight ? Colors.White : Ui.MicLine, beat));
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
                case "stop":
                {
                    // The square of a stop button: the session's turn is being ended.
                    Brush ink = inLight ? Brushes.White : (Brush)Ui.Alpha(Ui.Tint("failed"), 1);
                    dc.DrawRoundedRectangle(ink, null, new Rect(cx - 5, cy - 5, 10, 10), 2, 2);
                    break;
                }
                case "wait":
                {
                    // A clock with one hand going round: the words are held until the session
                    // has finished what it is doing.
                    Color ink = inLight ? Colors.White : Ui.MicLine;
                    double turn = t * 1.8;
                    dc.DrawEllipse(null, Ui.Line(ink, 0.95, 1.6), new Point(cx, cy), 7.2, 7.2);
                    dc.DrawLine(Ui.Line(ink, 1, 1.7), new Point(cx, cy), new Point(cx, cy - 4.8));
                    dc.DrawLine(Ui.Line(ink, 1, 1.7), new Point(cx, cy), new Point(cx + 3.6 * Math.Sin(turn), cy - 3.6 * Math.Cos(turn)));
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
        const int GWL_EXSTYLE = -20, GWL_STYLE = -16, WS_MINIMIZEBOX = 0x20000, WS_SYSMENU = 0x80000;
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
        bool settled;  // it has been fully open since it last opened: a new height is a resize, not an opening
        // How an open window takes a new height (overlay.resize): instant = at once; quick = it grows
        // at once, so nothing is cut off, and shrinks in about a tenth of a second.
        public static string Resize = "quick";
        FrameworkElement body;
        double speed;

        public Glass(double unfoldingWidth) : this(unfoldingWidth, false) { }

        // `takesInput`: a window to click and type in (the settings), not one to look through.
        public Glass(double unfoldingWidth, bool takesInput)
        {
            Unfolds = unfoldingWidth > 0;
            WindowStyle = WindowStyle.None;
            AllowsTransparency = true;
            Background = Brushes.Transparent;
            // The lights stay above everything. A window that takes input is a program's window
            // like any other: it can go behind others, has its place in the taskbar and in
            // Alt+Tab, and can be put away there.
            Topmost = !takesInput;
            ShowInTaskbar = takesInput;
            ShowActivated = takesInput;
            Focusable = takesInput;
            IsHitTestVisible = takesInput;
            // CanMinimize is what lets a click on its place in the taskbar put it away: Windows
            // only does that for a window that says it can be minimized. (The author: "if I click
            // the icon in the start bar it appears and if I click it again it doesn't disappear".)
            ResizeMode = takesInput ? ResizeMode.CanMinimize : ResizeMode.NoResize;
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
            // One that takes input is none of those.
            if (!takesInput) SetWindowLong(Handle, GWL_EXSTYLE, GetWindowLong(Handle, GWL_EXSTYLE) | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE);
            else SetWindowLong(Handle, GWL_STYLE, GetWindowLong(Handle, GWL_STYLE) | WS_MINIMIZEBOX | WS_SYSMENU);  // WPF leaves the second out of a window without a frame
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
            if (Goal == 0) settled = false;
            // Opening: a soft spring of about half a second. Already open, a new height (the history
            // of another session under the mouse) is taken at once: with the soft spring it never
            // caught up while the mouse went from row to row and what was below the old height
            // stayed cut off (the author, 2026-11-19: "if I move it real fast, there's a latency");
            // a quick spring of 60 ms was "better", and they wanted it "more responsive".
            // The author, asked which is the standard: under a tenth of a second reads as at once,
            // and an animation must not hold the words back; so quick grows at once and only the
            // shrinking moves ("Sure, yes").
            bool resizing = settled && Goal > 0;
            if (!moving || instantly || (resizing && (Resize == "instant" || Goal > Tall))) { Tall = Goal; speed = 0; if (Goal > 0) settled = true; }
            else if (resizing)
            {
                Tall += (Goal - Tall) * (1 - Math.Exp(-dt / 0.03));  // 95% of the way in 90 ms; a new goal takes over from wherever it is
                speed = 0;
                if (Math.Abs(Goal - Tall) < 0.4) Tall = Goal;
            }
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

    // The tool's mark: a disc in the author's blue (#006896) with five white voice bars of
    // uneven heights on its middle line, their ends cut on the slant. Drawn here and nowhere kept as a picture, so the
    // window, its place in the taskbar and the files for the README (`logo` message) are all
    // the same drawing. It is the one the author likes best of some thirty that were drawn
    // ("I would probably prefer E ... but it's not very creative, it's pretty anonymous"),
    // and it stands until a better one is found; CLAUDE.md has what was tried and what they
    // said of each (bars riding a wave "seems like stocks going up and down").
    static class Logo
    {
        static readonly double[] Bars = { 0.26, 0.50, 0.36, 0.62, 0.30 };  // each bar's height, as a share of the side

        // In a square of side `s`, from its corner. (`tile` is from when the taskbar had a
        // drawing of its own; there is one drawing now.)
        public static void Draw(DrawingContext dc, double s, bool tile)
        {
            // #006896 at the lower right; a lighter step of it at the upper left.
            var ink = new LinearGradientBrush(Color.FromRgb(0x2E, 0x9C, 0xC9), Color.FromRgb(0x00, 0x68, 0x96), new Point(0.15, 0), new Point(0.85, 1));
            ink.Freeze();
            dc.DrawEllipse(ink, null, new Point(s / 2, s / 2), s / 2, s / 2);
            // Each bar is cut on the slant at both ends, higher at its right: what makes the mark
            // less anonymous than plain round-ended bars (the author, of this one among six
            // drawn after the ideas behind well-known logos: "S6 is good").
            double wide = s * 0.094, apart = s * 0.148, cut = s * 0.04;
            var all = new StreamGeometry();
            using (StreamGeometryContext g = all.Open())
                for (int i = 0; i < Bars.Length; i++)
                {
                    double high = Bars[i] * s, x = s / 2 + (i - 2) * apart, top = s / 2 - high / 2, foot = s / 2 + high / 2;
                    g.BeginFigure(new Point(x - wide / 2, top + cut), true, true);
                    g.LineTo(new Point(x + wide / 2, top - cut), true, false);
                    g.LineTo(new Point(x + wide / 2, foot - cut), true, false);
                    g.LineTo(new Point(x - wide / 2, foot + cut), true, false);
                }
            all.Freeze();
            dc.DrawGeometry(Brushes.White, null, all);
        }

        public static BitmapSource Picture(int side, bool tile)
        {
            var visual = new DrawingVisual();
            using (DrawingContext dc = visual.RenderOpen()) Draw(dc, side, tile);
            var picture = new RenderTargetBitmap(side, side, 96, 96, PixelFormats.Pbgra32);
            picture.Render(visual);
            picture.Freeze();
            return picture;
        }

        public static void Save(string path, int side, bool tile)
        {
            var png = new PngBitmapEncoder();
            png.Frames.Add(BitmapFrame.Create(Picture(side, tile)));
            using (FileStream file = File.Create(path)) png.Save(file);
        }
    }

    class LogoMark : FrameworkElement
    {
        public LogoMark(double side) { Width = Height = side; }
        protected override void OnRender(DrawingContext dc) { Logo.Draw(dc, Width, false); }
    }

    // A switch: on or off.
    class Toggle : FrameworkElement
    {
        readonly bool on;
        public bool On { get { return on; } }

        public Toggle(bool on)
        {
            this.on = on;
            Width = 36; Height = 20;
            Cursor = Cursors.Hand;
            VerticalAlignment = VerticalAlignment.Center;
        }

        protected override void OnRender(DrawingContext dc)
        {
            dc.DrawRoundedRectangle(on ? Ui.Alpha(SettingsWindow.Accent, 0.95) : Ui.Paint("#33FFFFFF"), null, new Rect(0, 0, 36, 20), 10, 10);
            dc.DrawEllipse(on ? Brushes.White : Ui.Paint("#E6FFFFFF"), null, new Point(on ? 26 : 10, 10), 7.5, 7.5);
        }
    }

    // A number chosen by sliding: a thin track, filled up to a round knob. It reports every
    // value it passes (Moved, for the figure beside it) and the one it is let go at (Chosen).
    class Slide : FrameworkElement
    {
        const double Edge = 8;
        readonly double min, max, step;
        public double Value;
        public Action<double> Moved, Chosen;
        bool sliding;

        public Slide(double min, double max, double step, double value)
        {
            this.min = min; this.max = max; this.step = step > 0 ? step : 1;
            Value = Math.Max(min, Math.Min(max, value));
            Width = 150; Height = 22;
            Cursor = Cursors.Hand;
            VerticalAlignment = VerticalAlignment.Center;
        }

        protected override void OnRender(DrawingContext dc)
        {
            dc.DrawRectangle(Brushes.Transparent, null, new Rect(0, 0, Width, Height));  // all of it takes the mouse
            double share = max > min ? (Value - min) / (max - min) : 0, at = Edge + share * (Width - 2 * Edge);
            dc.DrawRoundedRectangle(Ui.Paint("#2EFFFFFF"), null, new Rect(Edge, 9, Width - 2 * Edge, 4), 2, 2);
            if (at > Edge) dc.DrawRoundedRectangle(Ui.Alpha(SettingsWindow.Accent, 0.95), null, new Rect(Edge, 9, at - Edge, 4), 2, 2);
            dc.DrawEllipse(Brushes.White, null, new Point(at, 11), sliding ? 7.5 : 6.5, sliding ? 7.5 : 6.5);
        }

        void Take(double x)
        {
            double share = Ui.Clamp((x - Edge) / (Width - 2 * Edge));
            double value = Math.Max(min, Math.Min(max, Math.Round((min + share * (max - min)) / step) * step));
            if (Math.Abs(value - Value) < 1e-9) return;
            Value = value;
            InvalidateVisual();
            if (Moved != null) Moved(value);
        }

        protected override void OnMouseLeftButtonDown(MouseButtonEventArgs e)
        {
            sliding = true;
            CaptureMouse();
            Take(e.GetPosition(this).X);
            InvalidateVisual();
            e.Handled = true;
        }

        protected override void OnMouseMove(MouseEventArgs e) { if (sliding) Take(e.GetPosition(this).X); }

        protected override void OnMouseLeftButtonUp(MouseButtonEventArgs e)
        {
            if (!sliding) return;
            sliding = false;
            ReleaseMouseCapture();
            InvalidateVisual();
            if (Chosen != null) Chosen(Value);
            e.Handled = true;
        }
    }

    // The settings window: sections down the left, the settings of one section on the right.
    // The only window of the overlay that takes the mouse and the keyboard. Like the rest it
    // decides nothing: the hub says what there is to set and what each thing is now (sections
    // of items: key, kind, name, help, value, and options or a range), a click sends back
    // "this key, this value", and the hub answers with how things stand, which is drawn.
    class SettingsWindow
    {
        public static readonly Color Accent = Color.FromRgb(0x00, 0x68, 0x96);  // the color of the tool's mark, the author's choice
        const double High = 560, Broad = 790, NavWidth = 176;
        // Resized from any edge or corner, and maximized (the author, 2026-11-20: "for settings
        // panel to be resizable and also to have like a maximized size button"). Maximized, the
        // settings keep a width they read well at (ListMost), in the middle of the right side.
        const double MinBroad = 700, MinHigh = 400, Edge = 6, ListMost = 760;
        bool maxed;
        Rect before;  // where it was before it was maximized
        Border maxButton;
        public readonly Glass Window = new Glass(0, true);
        readonly Action<string, object> choose;  // a setting was chosen
        readonly Action closed;                  // the window was closed from here
        readonly Action<bool> typingKey;         // a hotkey is being typed: the overlay's own hotkeys must let the keys through
        // A slider being moved, before it is let go: the overlay shows what that value looks like
        // at once, and the hub is told only on release (the author, 2026-11-21, of Glass: "it
        // updates only on release. Can you make it more responsive").
        public Action<string, double> Previewing;
        readonly StackPanel nav = new StackPanel { Margin = new Thickness(10, 2, 10, 12) };
        readonly StackPanel list = new StackPanel { Margin = new Thickness(18, 0, 22, 20) };
        readonly ScrollViewer scroll = new ScrollViewer { VerticalScrollBarVisibility = ScrollBarVisibility.Hidden, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, Focusable = false };
        readonly Border thumb = new Border { Width = 3, CornerRadius = new CornerRadius(1.5), Background = Ui.Paint("#4DFFFFFF"), HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Top, Margin = new Thickness(0, 0, 7, 0), Visibility = Visibility.Collapsed, IsHitTestVisible = false };
        readonly TextBlock title = new TextBlock { Text = "Sidetone" };  // the tool's name, as the hub gives it
        object[] sections = new object[0];
        string current = "", capturing = "";
        bool placed;

        public SettingsWindow(Action<string, object> choose, Action closed, Action<bool> typingKey)
        {
            this.choose = choose; this.closed = closed; this.typingKey = typingKey;
            Window.SizeToContent = SizeToContent.Manual;
            Window.Width = Broad; Window.Height = High;
            Window.Title = "Sidetone settings";
            Window.Icon = Logo.Picture(256, true);

            // Two columns over the whole height: the sections at the left on a darker ground of
            // their own (the author: "the menu ... a different background color to compare to
            // the right"), what one section holds at the right. The window is moved by the top
            // of either.
            var root = new Grid();
            root.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(NavWidth) });
            root.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            MouseButtonEventHandler move = delegate(object sender, MouseButtonEventArgs e)
            {
                if (e.ClickCount == 2) { ToggleMax(); return; }  // as a window's title bar does
                if (maxed)  // dragged away from maximized: back to its size, under the mouse where it was held
                {
                    Point at = e.GetPosition(Window), screen = OnScreen(e);
                    double share = at.X / Math.Max(1, Window.Width);
                    ToggleMax();
                    Window.Left = screen.X - share * Window.Width;
                    Window.Top = screen.Y - at.Y;
                }
                try { Window.DragMove(); } catch (InvalidOperationException) { }
            };

            var side = new Grid();
            side.RowDefinitions.Add(new RowDefinition { Height = new GridLength(54) });
            side.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
            side.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            // The tool's mark and name head the menu (the author: not "Settings" there, the name).
            var brand = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(20, 8, 0, 0) };
            brand.Children.Add(new LogoMark(24) { VerticalAlignment = VerticalAlignment.Center });
            title.FontSize = 15; title.FontWeight = FontWeights.SemiBold; title.VerticalAlignment = VerticalAlignment.Center; title.Margin = new Thickness(9, 0, 0, 1);
            brand.Children.Add(title);
            var name = new Border { Background = Brushes.Transparent, Child = brand };
            name.MouseLeftButtonDown += move;
            side.Children.Add(name);
            Grid.SetRow(nav, 1);
            side.Children.Add(nav);
            root.Children.Add(new Border { Background = Ui.Paint("#47000000"), BorderBrush = Ui.Paint("#14FFFFFF"), BorderThickness = new Thickness(0, 0, 1, 0), Child = side });

            var main = new Grid();
            main.RowDefinitions.Add(new RowDefinition { Height = new GridLength(44) });
            main.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
            var head = new Grid { Background = Brushes.Transparent };
            head.MouseLeftButtonDown += move;
            var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 4, 10, 0) };
            buttons.Children.Add(HeadButton("M0,5 L9,5", delegate { Window.WindowState = WindowState.Minimized; }));
            maxButton = HeadButton(MaxSign, delegate { ToggleMax(); });
            buttons.Children.Add(maxButton);
            buttons.Children.Add(HeadButton("M0,0 L9,9 M9,0 L0,9", delegate { Close(); }));
            head.Children.Add(buttons);
            main.Children.Add(head);
            scroll.Content = list;
            scroll.ScrollChanged += delegate { ShowThumb(); };
            Grid.SetRow(scroll, 1);
            main.Children.Add(scroll);
            Grid.SetRow(thumb, 1);
            main.Children.Add(thumb);
            Grid.SetColumn(main, 1);
            root.Children.Add(main);

            list.MaxWidth = ListMost;
            // Stretched, so every section is as wide as the window lets it be (up to ListMost, then
            // in the middle), whether its lines are long or short: Voices, with short lines, stood
            // narrow in the middle (the author, 2026-11-21: "they should take up the spaces like
            // the rest of the setting pages").
            list.HorizontalAlignment = HorizontalAlignment.Stretch;
            var frame = new Grid();
            frame.Children.Add(root);
            AddGrips(frame);
            Window.Panel.Child = frame;
            Window.PreviewKeyDown += OnKey;
            Window.Deactivated += delegate { if (capturing.Length > 0) StopTyping(); };
        }

        const string MaxSign = "M0.5,0.5 L8.5,0.5 L8.5,8.5 L0.5,8.5 Z", RestoreSign = "M2.5,0.5 L8.5,0.5 L8.5,6.5 M0.5,2.5 L6.5,2.5 L6.5,8.5 L0.5,8.5 Z";

        // Maximized to the work area of the screen it is on, or back to where it was.
        void ToggleMax()
        {
            if (maxed)
            {
                maxed = false;
                Window.Left = before.Left; Window.Top = before.Top; Window.Width = before.Width; Window.Height = before.Height;
            }
            else
            {
                before = new Rect(Window.Left, Window.Top, Window.Width, Window.Height);
                System.Drawing.Rectangle area = System.Windows.Forms.Screen.FromHandle(Window.Handle).WorkingArea;
                Matrix fromDevice = HwndSource.FromHwnd(Window.Handle).CompositionTarget.TransformFromDevice;
                Point a = fromDevice.Transform(new Point(area.Left, area.Top)), b = fromDevice.Transform(new Point(area.Right, area.Bottom));
                Window.Left = a.X; Window.Top = a.Y; Window.Width = b.X - a.X; Window.Height = b.Y - a.Y;
                maxed = true;
            }
            ((System.Windows.Shapes.Path)maxButton.Child).Data = Geometry.Parse(maxed ? RestoreSign : MaxSign);
            scroll.UpdateLayout();
            ShowThumb();
        }

        // Where the mouse is, in the units the window is placed in.
        Point OnScreen(MouseEventArgs e)
        {
            Point device = Window.PointToScreen(e.GetPosition(Window));
            return HwndSource.FromHwnd(Window.Handle).CompositionTarget.TransformFromDevice.Transform(device);
        }

        // A thin strip along each edge and a square at each corner, which the window is resized by.
        // The corners come last, so they are on top of the strips.
        void AddGrips(Grid frame)
        {
            foreach (string side in new[] { "W", "E", "N", "S", "NW", "NE", "SW", "SE" })
            {
                bool west = side.Contains("W"), east = side.Contains("E"), north = side.Contains("N"), south = side.Contains("S");
                var grip = new Border { Background = Brushes.Transparent };
                grip.HorizontalAlignment = west ? HorizontalAlignment.Left : east ? HorizontalAlignment.Right : HorizontalAlignment.Stretch;
                grip.VerticalAlignment = north ? VerticalAlignment.Top : south ? VerticalAlignment.Bottom : VerticalAlignment.Stretch;
                if (west || east) grip.Width = side.Length == 2 ? Edge * 2 : Edge;
                if (north || south) grip.Height = side.Length == 2 ? Edge * 2 : Edge;
                grip.Cursor = (west && north) || (east && south) ? Cursors.SizeNWSE : (east && north) || (west && south) ? Cursors.SizeNESW
                    : west || east ? Cursors.SizeWE : Cursors.SizeNS;
                Point start = new Point();
                Rect from = Rect.Empty;
                grip.MouseLeftButtonDown += delegate(object sender, MouseButtonEventArgs e)
                {
                    e.Handled = true;
                    if (maxed) return;
                    start = OnScreen(e);
                    from = new Rect(Window.Left, Window.Top, Window.Width, Window.Height);
                    grip.CaptureMouse();
                };
                grip.MouseMove += delegate(object sender, MouseEventArgs e)
                {
                    if (!grip.IsMouseCaptured) return;
                    Point now = OnScreen(e);
                    double dx = now.X - start.X, dy = now.Y - start.Y, left = from.Left, top = from.Top, wide = from.Width, high = from.Height;
                    if (east) wide = Math.Max(MinBroad, from.Width + dx);
                    if (south) high = Math.Max(MinHigh, from.Height + dy);
                    if (west) { wide = Math.Max(MinBroad, from.Width - dx); left = from.Right - wide; }
                    if (north) { high = Math.Max(MinHigh, from.Height - dy); top = from.Bottom - high; }
                    Window.Left = left; Window.Top = top; Window.Width = wide; Window.Height = high;
                    ShowThumb();
                };
                grip.MouseLeftButtonUp += delegate { grip.ReleaseMouseCapture(); };
                frame.Children.Add(grip);
            }
        }

        // One of the small buttons at the top right: a sign drawn with a few strokes.
        static Border HeadButton(string strokes, Action pressed)
        {
            var sign = new System.Windows.Shapes.Path { Data = Geometry.Parse(strokes), Stroke = Ui.Dim, StrokeThickness = 1.4, StrokeStartLineCap = PenLineCap.Round, StrokeEndLineCap = PenLineCap.Round, Width = 9, Height = 9, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center };
            var button = new Border { Width = 30, Height = 30, CornerRadius = new CornerRadius(7), Margin = new Thickness(2, 0, 0, 0), Cursor = Cursors.Hand, Child = sign };
            Lit(button, "#00FFFFFF", "#24FFFFFF");
            button.MouseLeftButtonDown += delegate(object sender, MouseButtonEventArgs e) { e.Handled = true; };  // not the start of a move
            button.MouseLeftButtonUp += delegate { pressed(); };
            return button;
        }

        public bool IsOpen { get { return Window.IsVisible; } }

        // In front of you, to be typed in: not behind another program, not put away.
        public bool InFront { get { return Window.IsVisible && Window.IsActive && Window.WindowState != WindowState.Minimized; } }

        public void Look(string kind)
        {
            Window.Look(kind);
            // Denser than the lights: this is read for minutes, over whatever is behind it.
            if (kind != "solid") Window.Panel.Background = Ui.Paint(kind == "none" ? "#F51A1D24" : "#E01A1D24");
        }

        // `area`: the part of the screen it may open in the middle of.
        // `quiet`: shown without taking the keyboard (for pictures of it).
        public void Show(object[] sections, string section, Rect area, bool quiet, string name)
        {
            this.sections = sections;
            if (name.Length > 0) { title.Text = name; Window.Title = name + " settings"; }
            var names = new List<string>();
            foreach (object o in sections) names.Add(Overlay.Str((Dictionary<string, object>)o, "name"));
            if (section.Length > 0 && names.Contains(section)) { if (section != current) scroll.ScrollToVerticalOffset(0); current = section; }
            if (!names.Contains(current)) current = names.Count > 0 ? names[0] : "";
            Fill();
            if (!Window.IsVisible)
            {
                if (!placed)
                {
                    Window.Left = area.Left + Math.Max(0, (area.Width - Broad) / 2);
                    Window.Top = area.Top + Math.Max(0, (area.Height - High) / 2);
                    placed = true;
                }
                Window.ShowActivated = !quiet;
                Window.Show();
            }
            if (quiet) return;
            if (Window.WindowState == WindowState.Minimized) Window.WindowState = WindowState.Normal;
            // Asked for with the command and not the key, Windows does not let it take the
            // keyboard from the program in front, and it opened behind that program, unseen
            // (the author: "I don't see it open"). Being on top for a moment brings it up.
            Window.Topmost = true;
            Window.Topmost = false;
            Window.Activate();
        }

        // A click at a place in the window, as the mouse would make it, without the mouse: for
        // checking from outside that what is drawn there answers to it.
        public void Click(double x, double y)
        {
            Window.UpdateLayout();
            HitTestResult hit = VisualTreeHelper.HitTest(Window.Panel, new Point(x, y));
            var under = hit == null ? null : hit.VisualHit as UIElement;
            if (under == null) return;
            foreach (RoutedEvent step in new[] { Mouse.MouseDownEvent, Mouse.MouseUpEvent })
                under.RaiseEvent(new MouseButtonEventArgs(Mouse.PrimaryDevice, Environment.TickCount, MouseButton.Left) { RoutedEvent = step });
        }

        public void Hide()
        {
            if (capturing.Length > 0) StopTyping();
            ForgetPlaces(null);
            if (Window.IsVisible) Window.Hide();
        }

        void Close()
        {
            Hide();
            closed();
        }

        void StopTyping()
        {
            capturing = "";
            typingKey(false);
            Fill();
        }

        // A background that answers to the mouse being on it.
        static void Lit(Border box, string rest, string under)
        {
            Brush plain = Ui.Paint(rest), bright = Ui.Paint(under);
            box.Background = plain;
            box.MouseEnter += delegate { box.Background = bright; };
            box.MouseLeave += delegate { box.Background = plain; };
        }

        static bool Same(object a, object b)
        {
            return Convert.ToString(a, CultureInfo.InvariantCulture) == Convert.ToString(b, CultureInfo.InvariantCulture);
        }

        void ShowThumb()
        {
            bool more = scroll.ExtentHeight > scroll.ViewportHeight + 1;
            thumb.Visibility = more ? Visibility.Visible : Visibility.Collapsed;
            if (!more) return;
            thumb.Height = Math.Max(24, scroll.ViewportHeight * scroll.ViewportHeight / scroll.ExtentHeight);
            double room = scroll.ViewportHeight - thumb.Height, far = scroll.ExtentHeight - scroll.ViewportHeight;
            thumb.Margin = new Thickness(0, far > 0 ? room * scroll.VerticalOffset / far : 0, 7, 0);
        }

        // Draws the sections at the left and the settings of the one that is chosen.
        void Fill()
        {
            nav.Children.Clear();
            list.Children.Clear();
            foreach (object o in sections)
            {
                var section = (Dictionary<string, object>)o;
                string name = Overlay.Str(section, "name");
                bool on = name == current;
                var entry = new Border { CornerRadius = new CornerRadius(7), Padding = new Thickness(12, 7, 12, 8), Margin = new Thickness(0, 1, 0, 1), Cursor = Cursors.Hand };
                entry.Child = new TextBlock { Text = name, FontSize = 13, FontWeight = on ? FontWeights.SemiBold : FontWeights.Normal, Foreground = on ? Brushes.White : Ui.Dim };
                if (on) entry.Background = Ui.Paint("#24FFFFFF");
                else
                {
                    Lit(entry, "#00FFFFFF", "#12FFFFFF");
                    entry.MouseLeftButtonUp += delegate { if (capturing.Length > 0) StopTyping(); current = name; scroll.ScrollToVerticalOffset(0); Fill(); };
                }
                nav.Children.Add(entry);
                if (!on) continue;

                list.Children.Add(new TextBlock { Text = name, FontSize = 19, FontWeight = FontWeights.SemiBold, Margin = new Thickness(6, 0, 0, 12) });
                object[] items = section.ContainsKey("items") && section["items"] is object[] ? (object[])section["items"] : new object[0];
                // The voices of each language that are ticked, in their order: what a drag reorders.
                ticked.Clear();
                foreach (object i in items)
                {
                    var item = (Dictionary<string, object>)i;
                    if (Overlay.Str(item, "kind") != "voice" || Folded(item)) continue;
                    string group = Overlay.Str(item, "group");
                    if (!ticked.ContainsKey(group)) ticked[group] = new List<string>();
                    ticked[group].Add(Overlay.Str(item, "voice"));
                }
                items = KeepPlaces(items);
                StackPanel lines = null;
                string inGroup = "";
                int hidden = 0, folded = 0;
                bool shut = false, folding = false;
                // A card ends at a heading or at the end: with a line to unfold what it keeps folded.
                Action endCard = delegate
                {
                    if (lines == null) return;
                    string group = inGroup;
                    if (folded > 0)
                    {
                        bool open = hidden == 0;
                        if (lines.Children.Count > 0) lines.Children.Add(new Border { Height = 1, Background = Ui.Paint("#14FFFFFF"), Margin = new Thickness(16, 0, 0, 0) });
                        var more = new Border { Padding = new Thickness(16, 9, 14, 10), Cursor = Cursors.Hand, CornerRadius = new CornerRadius(0, 0, 10, 10) };
                        more.Child = new TextBlock { Text = open ? "Fewer Voices" : "More Voices (" + hidden + ")", FontSize = 12, Foreground = Ui.Dim };
                        Lit(more, "#00FFFFFF", "#0FFFFFFF");
                        more.MouseLeftButtonUp += delegate { if (open) unfolded.Remove(group); else unfolded.Add(group); Fill(); };
                        lines.Children.Add(more);
                    }
                    list.Children.Add(new Border { CornerRadius = new CornerRadius(10), Background = Ui.Paint("#12FFFFFF"), Child = lines, Margin = new Thickness(0, 0, 0, folding ? 8 : 4) });
                    // 8 under an open language's card, as under a closed heading: with 4 the gap to the
                    // next language was half the others (the author, 2026-11-21: "not very coherent").
                    lines = null;
                };
                foreach (object i in items)
                {
                    var item = (Dictionary<string, object>)i;
                    if (Overlay.Str(item, "kind") == "intro")  // a sentence for the whole page, under its title
                    {
                        list.Children.Add(new TextBlock { Text = Overlay.Str(item, "help"), FontSize = 11.5, Foreground = Ui.Faint, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(6, -6, 0, 14) });
                        continue;
                    }
                    if (Overlay.Str(item, "kind") == "heading")
                    {
                        endCard();
                        inGroup = Overlay.Str(item, "key").Replace("heading.", "");
                        hidden = folded = 0;
                        shut = false;
                        folding = item.ContainsKey("fold") && Convert.ToBoolean(item["fold"], CultureInfo.InvariantCulture);
                        if (item.ContainsKey("fold") && Convert.ToBoolean(item["fold"], CultureInfo.InvariantCulture))
                        {
                            bool spoken = !item.ContainsKey("spoken") || Convert.ToBoolean(item["spoken"], CultureInfo.InvariantCulture);
                            shut = !spoken || !openGroups.Contains(inGroup);
                            list.Children.Add(FoldHead(inGroup, Overlay.Str(item, "name"), Overlay.Str(item, "summary"), !shut,
                                Overlay.Str(item, "speak"), spoken, item.ContainsKey("last") && Convert.ToBoolean(item["last"], CultureInfo.InvariantCulture)));
                            continue;
                        }
                        bool first = list.Children.Count == 1;
                        list.Children.Add(new TextBlock { Text = Overlay.Str(item, "name"), FontSize = 14, FontWeight = FontWeights.SemiBold, Margin = new Thickness(6, first ? 0 : 22, 0, 2) });
                        string about = Overlay.Str(item, "help");
                        if (about.Length > 0) list.Children.Add(new TextBlock { Text = about, FontSize = 11.5, Foreground = Ui.Faint, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(6, 0, 0, 9) });
                        continue;
                    }
                    if (shut) continue;  // under a closed heading
                    if (lines == null) lines = new StackPanel();
                    if (Folded(item) && !Kept(item))
                    {
                        folded++;
                        if (!unfolded.Contains(Overlay.Str(item, "group"))) { hidden++; continue; }
                    }
                    if (lines.Children.Count > 0) lines.Children.Add(new Border { Height = 1, Background = Ui.Paint("#14FFFFFF"), Margin = new Thickness(16, 0, 0, 0) });
                    lines.Children.Add(Line(item, lines));
                }
                endCard();
                if (section.ContainsKey("resettable") && Convert.ToBoolean(section["resettable"], CultureInfo.InvariantCulture))
                    list.Children.Add(ResetButton(name, section.ContainsKey("changed") && Convert.ToBoolean(section["changed"], CultureInfo.InvariantCulture)));
            }
            scroll.UpdateLayout();
            ShowThumb();
        }

        // Under a section's card: its settings back as a new install has them (the author,
        // 2026-11-20: "for each category ... a reset button at the end"). Faint while nothing
        // differs; the first click asks, the second within 4 s resets.
        string confirming = "";
        UIElement ResetButton(string section, bool changed)
        {
            bool asking = changed && confirming == section;
            var button = new Border { CornerRadius = new CornerRadius(7), Padding = new Thickness(13, 6, 13, 7), Margin = new Thickness(0, 14, 0, 0), HorizontalAlignment = HorizontalAlignment.Left };
            button.Child = new TextBlock { Text = asking ? "Click Again to Reset" : "Reset", FontSize = 12, FontWeight = asking ? FontWeights.SemiBold : FontWeights.Normal, Foreground = changed ? (asking ? Brushes.White : Ui.Dim) : Ui.Faint };
            if (!changed)
            {
                button.Background = Ui.Paint("#08FFFFFF");
                button.ToolTip = "Everything here is as it comes";
                return button;
            }
            button.Cursor = Cursors.Hand;
            if (asking) button.Background = new SolidColorBrush(Color.FromArgb(0xB0, Accent.R, Accent.G, Accent.B));
            else Lit(button, "#12FFFFFF", "#22FFFFFF");
            button.MouseLeftButtonUp += delegate
            {
                if (confirming == section) { confirming = ""; choose("reset", section); return; }
                confirming = section;
                var wait = new DispatcherTimer { Interval = TimeSpan.FromSeconds(4) };
                wait.Tick += delegate { wait.Stop(); if (confirming == section) { confirming = ""; Fill(); } };
                wait.Start();
                Fill();
            };
            return button;
        }

        // Voices: which groups show what they keep folded, and the ticked voices of each in order.
        readonly HashSet<string> unfolded = new HashSet<string>();
        readonly Dictionary<string, List<string>> ticked = new Dictionary<string, List<string>>();

        static bool Folded(Dictionary<string, object> item)
        {
            return item.ContainsKey("more") && Convert.ToBoolean(item["more"], CultureInfo.InvariantCulture);
        }

        // A voice unticked while its language is open stays where it was, without its tick, until
        // the language or the window is closed; only then does it go under More Voices (the
        // author, 2026-11-21: "whenever I untick a voice it immediately goes to like more
        // voices"). `places` is, by language, the order of the voices at the top of its card (the
        // ticked and those kept) since the first untick; `kept` the voices unticked meanwhile.
        readonly Dictionary<string, List<string>> places = new Dictionary<string, List<string>>();
        readonly HashSet<string> kept = new HashSet<string>();

        bool Kept(Dictionary<string, object> item)
        {
            return kept.Contains(Overlay.Str(item, "group") + "/" + Overlay.Str(item, "voice"));
        }

        void ForgetPlaces(string group)  // null: every language
        {
            if (group == null) { places.Clear(); kept.Clear(); return; }
            places.Remove(group);
            kept.RemoveWhere(delegate(string k) { return k.StartsWith(group + "/", StringComparison.Ordinal); });
        }

        // The voices at the top of a language's card, in the order shown: what a drag moves among.
        List<string> Block(string group)
        {
            List<string> now, was;
            if (!ticked.TryGetValue(group, out now)) now = new List<string>();
            if (!places.TryGetValue(group, out was)) return new List<string>(now);
            var block = new List<string>();
            foreach (string v in was) if (now.Contains(v) || kept.Contains(group + "/" + v)) block.Add(v);
            foreach (string v in now) if (!block.Contains(v)) block.Add(v);  // ticked from More Voices since
            return block;
        }

        // The hub lists the ticked first and the rest after; a language with kept voices is put
        // back in the order of its block, the others after it as the hub has them.
        object[] KeepPlaces(object[] items)
        {
            if (places.Count == 0) return items;
            var result = new List<object>();
            int i = 0;
            while (i < items.Length)
            {
                var item = (Dictionary<string, object>)items[i];
                string group = Overlay.Str(item, "group");
                if (Overlay.Str(item, "kind") != "voice" || !places.ContainsKey(group)) { result.Add(item); i++; continue; }
                var run = new List<Dictionary<string, object>>();
                while (i < items.Length && Overlay.Str((Dictionary<string, object>)items[i], "kind") == "voice" && Overlay.Str((Dictionary<string, object>)items[i], "group") == group)
                    run.Add((Dictionary<string, object>)items[i++]);
                foreach (string v in Block(group))
                    foreach (var r in run) if (Overlay.Str(r, "voice") == v) result.Add(r);
                List<string> block = Block(group);
                foreach (var r in run) if (!block.Contains(Overlay.Str(r, "voice"))) result.Add(r);
            }
            return result.ToArray();
        }

        // A tick clicked. Unticked, the voice keeps its place; ticked again, it goes back to it.
        void Tick(string key, string group, string voice, bool on)
        {
            string id = group + "/" + voice;
            List<string> now;
            if (on)
            {
                if (ticked.TryGetValue(group, out now) && now.Count > 1)  // the last one cannot go
                {
                    if (!places.ContainsKey(group)) places[group] = Block(group);
                    kept.Add(id);
                }
                choose(key, false);
                return;
            }
            if (!kept.Remove(id)) { choose(key, true); return; }
            var order = new List<string>();
            if (!ticked.TryGetValue(group, out now)) now = new List<string>();
            foreach (string v in places[group])
                if (v == voice || now.Contains(v)) order.Add(v);
            foreach (string v in now) if (!order.Contains(v)) order.Add(v);
            choose("voices_order." + group, order.ToArray());
        }

        // Which headings that open and close are open: all closed at first, so every language
        // can be seen at once (the author, 2026-11-21).
        readonly HashSet<string> openGroups = new HashSet<string>();

        // A heading that opens and closes the card under it: a chevron, its name, and at the
        // right while it is closed what it holds ("4 selected"); open, the card below says it.
        // With `speak`, a switch at the far right for whether you speak the language (the author,
        // 2026-11-21: "if someone speaks only English, they should be able to disable the other
        // languages"): off, the heading is dim and does not open; the last one on cannot go off.
        UIElement FoldHead(string group, string name, string summary, bool open, string speak, bool spoken, bool last)
        {
            var row = new Grid();
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            var chevron = new System.Windows.Shapes.Path { Data = Geometry.Parse(open ? "M0,0 L4.5,4.5 L9,0" : "M0,0 L4.5,4.5 L0,9"), Stroke = Ui.Dim, StrokeThickness = 1.5, StrokeStartLineCap = PenLineCap.Round, StrokeEndLineCap = PenLineCap.Round, StrokeLineJoin = PenLineJoin.Round, Width = 10, Height = 10, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, open ? 3 : 0, 12, 0) };
            row.Children.Add(chevron);
            var title = new TextBlock { Text = name, FontSize = 14, FontWeight = FontWeights.SemiBold, VerticalAlignment = VerticalAlignment.Center };
            Grid.SetColumn(title, 1);
            row.Children.Add(title);
            var holds = new TextBlock { Text = summary, Visibility = open ? Visibility.Collapsed : Visibility.Visible, FontSize = 12, Foreground = Ui.Faint, TextTrimming = TextTrimming.CharacterEllipsis, HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(18, 0, 0, 0) };
            Grid.SetColumn(holds, 2);
            row.Children.Add(holds);
            var head = new Border { CornerRadius = new CornerRadius(10), Padding = new Thickness(16, 12, 16, 12), Margin = new Thickness(0, 0, 0, open ? 6 : 8), Cursor = Cursors.Hand, Child = row };
            if (speak.Length > 0)
            {
                var toggle = new Toggle(spoken) { Margin = new Thickness(16, -2, -2, -2),  // -2: in line with the voices' switches below (measured)
                    Opacity = last ? 0.45 : 1,
                    ToolTip = last ? "Push-to-talk needs at least one language" : spoken ? "You speak it: push-to-talk listens for it" : "Turn on if you speak it" };
                ToolTipService.SetShowOnDisabled(toggle, true);
                toggle.MouseLeftButtonUp += delegate(object sender, MouseButtonEventArgs e) { e.Handled = true; if (!last) choose(speak, !spoken); };
                toggle.MouseLeftButtonDown += delegate(object sender, MouseButtonEventArgs e) { e.Handled = true; };
                Grid.SetColumn(toggle, 3);
                row.Children.Add(toggle);
            }
            if (!spoken)  // not spoken: dim, and nothing to open
            {
                chevron.Opacity = title.Opacity = 0.4;
                head.Cursor = Cursors.Arrow;
                head.Background = Ui.Paint("#0AFFFFFF");
                return head;
            }
            Lit(head, open ? "#1AFFFFFF" : "#12FFFFFF", "#22FFFFFF");
            head.MouseLeftButtonUp += delegate { if (open) { openGroups.Remove(group); ForgetPlaces(group); } else openGroups.Add(group); Fill(); };
            return head;
        }

        // A round button with a triangle: the voice says a sentence, and nothing is changed. While
        // that sentence plays it shows a square, and a click on it stops it (the author,
        // 2026-11-21: "click it, the preview goes, and then there's the square to stop it").
        Border PlayButton(string voice, bool playing)
        {
            var sign = new System.Windows.Shapes.Path { Data = Geometry.Parse(playing ? "M0,0 L8,0 L8,8 L0,8 Z" : "M0,0 L7,4.5 L0,9 Z"), Fill = playing ? Brushes.White : Ui.Dim, Width = playing ? 8 : 7, Height = playing ? 8 : 9, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(playing ? 0 : 2, 0, 0, 0) };
            var button = new Border { Width = 28, Height = 28, CornerRadius = new CornerRadius(14), Cursor = Cursors.Hand, Child = sign, ToolTip = playing ? "Stop" : "Hear It" };
            if (playing) button.Background = Ui.Alpha(Accent, 0.85);
            else Lit(button, "#17FFFFFF", "#2EFFFFFF");
            button.MouseLeftButtonDown += delegate(object sender, MouseButtonEventArgs e) { e.Handled = true; };
            button.MouseLeftButtonUp += delegate(object sender, MouseButtonEventArgs e) { e.Handled = true; choose(playing ? "stop_preview" : "play", voice); };
            return button;
        }

        // Six dots at the left of a ticked voice, where it is held to be dragged.
        static Border Grip()
        {
            var dots = new Canvas { Width = 8, Height = 12 };
            for (int r = 0; r < 3; r++)
                for (int c = 0; c < 2; c++)
                {
                    var dot = new System.Windows.Shapes.Ellipse { Width = 2.6, Height = 2.6, Fill = Ui.Faint };
                    Canvas.SetLeft(dot, c * 5); Canvas.SetTop(dot, r * 4.6);
                    dots.Children.Add(dot);
                }
            return new Border { Background = Brushes.Transparent, Padding = new Thickness(0, 6, 12, 6), Cursor = Cursors.SizeNS, VerticalAlignment = VerticalAlignment.Center, Child = dots, ToolTip = "Drag to Change the Order" };
        }

        // A ticked voice dragged up or down among the ticked voices of its language: the others
        // make room as it passes, and where it is let go is its new place, sent to the hub.
        void Drag(Border grip, Grid line, StackPanel card, string group, string voice)
        {
            double startY = 0, pitch = 0;
            int from = -1, to = -1;
            var rows = new List<FrameworkElement>();
            grip.MouseLeftButtonDown += delegate(object sender, MouseButtonEventArgs e)
            {
                e.Handled = true;
                List<string> order = Block(group);
                if (order.Count < 2) return;
                rows.Clear();
                foreach (UIElement child in card.Children)
                    if (child is Grid) rows.Add((FrameworkElement)child);
                rows = rows.GetRange(0, Math.Min(order.Count, rows.Count));  // the ticked (and the kept) come first
                from = to = rows.IndexOf(line);
                if (from < 0) return;
                pitch = line.ActualHeight + line.Margin.Top + line.Margin.Bottom + 1;  // a line and the rule under it
                startY = e.GetPosition(card).Y;
                Panel.SetZIndex(line, 5);
                grip.CaptureMouse();
            };
            grip.MouseMove += delegate(object sender, MouseEventArgs e)
            {
                if (!grip.IsMouseCaptured || from < 0) return;
                double dy = e.GetPosition(card).Y - startY;
                dy = Math.Max(-from * pitch, Math.Min((rows.Count - 1 - from) * pitch, dy));
                line.RenderTransform = new TranslateTransform(0, dy);
                to = Math.Max(0, Math.Min(rows.Count - 1, from + (int)Math.Round(dy / pitch)));
                for (int k = 0; k < rows.Count; k++)
                {
                    if (k == from) continue;
                    double shift = from < to && k > from && k <= to ? -pitch : from > to && k < from && k >= to ? pitch : 0;
                    rows[k].RenderTransform = new TranslateTransform(0, shift);
                }
            };
            grip.MouseLeftButtonUp += delegate
            {
                if (!grip.IsMouseCaptured) return;
                grip.ReleaseMouseCapture();
                foreach (FrameworkElement row in rows) row.RenderTransform = null;
                Panel.SetZIndex(line, 0);
                if (from < 0 || to == from) return;
                var order = Block(group);
                order.Remove(voice);
                order.Insert(to, voice);
                if (places.ContainsKey(group)) places[group] = new List<string>(order);
                var now = ticked[group];
                order.RemoveAll(delegate(string v) { return !now.Contains(v); });  // the kept are not sent
                ticked[group] = order;
                choose("voices_order." + group, order.ToArray());
            };
        }

        // A small rounded word with an i in a circle, which says what it means when the mouse rests
        // on it ("Faster" after Piper's voices; the author, 2026-11-21: "an info icon on why").
        static Border Tag(string word, string meaning)
        {
            var inside = new StackPanel { Orientation = Orientation.Horizontal };
            inside.Children.Add(new TextBlock { Text = word, FontSize = 10.5, Foreground = Ui.Dim, VerticalAlignment = VerticalAlignment.Center });
            var info = new Grid { Width = 11, Height = 11, Margin = new Thickness(5, 0, 0, 0), VerticalAlignment = VerticalAlignment.Center };
            info.Children.Add(new System.Windows.Shapes.Ellipse { Stroke = Ui.Dim, StrokeThickness = 1 });
            info.Children.Add(new TextBlock { Text = "i", FontSize = 8, FontWeight = FontWeights.SemiBold, Foreground = Ui.Dim, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 0, 1) });
            inside.Children.Add(info);
            var tip = new ToolTip { Content = new TextBlock { Text = meaning, TextWrapping = TextWrapping.Wrap, MaxWidth = 280 } };
            var pill = new Border { CornerRadius = new CornerRadius(5), Padding = new Thickness(6, 1, 5, 2), Margin = new Thickness(8, 0, 0, 0), Background = Ui.Paint("#1AFFFFFF"), Child = inside, Cursor = Cursors.Help, ToolTip = tip, VerticalAlignment = VerticalAlignment.Center };
            ToolTipService.SetInitialShowDelay(pill, 150);
            // Down a pixel: centered, its word sat 1 px above the description's line (measured in a
            // picture; the author, 2026-11-21: "the text is not very centered with the rest").
            pill.RenderTransform = new TranslateTransform(0, 1);
            return pill;
        }

        // One setting: its name and a sentence about it at the left, what sets it at the right.
        UIElement Line(Dictionary<string, object> item, StackPanel card)
        {
            string key = Overlay.Str(item, "key"), kind = Overlay.Str(item, "kind"), help = Overlay.Str(item, "help");
            object value = item.ContainsKey("value") ? item["value"] : null;
            object[] options = item.ContainsKey("options") && item["options"] is object[] ? (object[])item["options"] : new object[0];
            bool typing = kind == "key" && capturing == key;
            var line = new Grid { Margin = new Thickness(16, 10, 14, 11) };
            line.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            line.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            var words = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
            if (kind == "voice" && (!Folded(item) || Kept(item)))  // a ticked voice, or one just unticked: dragged by its grip
            {
                line.ColumnDefinitions.Insert(0, new ColumnDefinition { Width = GridLength.Auto });
                var grip = Grip();
                line.Children.Add(grip);
                Grid.SetColumn(words, 1);
                Drag(grip, line, card, Overlay.Str(item, "group"), Overlay.Str(item, "voice"));
            }
            words.Children.Add(new TextBlock { Text = Overlay.Str(item, "name"), FontSize = 13, TextTrimming = TextTrimming.CharacterEllipsis });
            if (typing) help = "Press the new keys. Esc keeps the old ones, Delete leaves it without a key.";
            string tag = Overlay.Str(item, "tag");
            if (tag.Length > 0)  // a voice's description with a word after it that explains itself under the mouse
            {
                var row = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 2, 0, 0) };
                if (help.Length > 0) row.Children.Add(new TextBlock { Text = help, FontSize = 11.5, Foreground = Ui.Faint, VerticalAlignment = VerticalAlignment.Center });
                row.Children.Add(Tag(tag, Overlay.Str(item, "tag_help")));
                words.Children.Add(row);
            }
            else if (help.Length > 0) words.Children.Add(new TextBlock { Text = help, FontSize = 11.5, Foreground = typing ? Ui.Dim : Ui.Faint, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 2, 0, 0) });
            line.Children.Add(words);

            FrameworkElement control;
            if (kind == "switch")
            {
                bool on = value != null && Convert.ToBoolean(value, CultureInfo.InvariantCulture);
                control = new Toggle(on);
                control.MouseLeftButtonUp += delegate { choose(key, !on); };
            }
            else if (kind == "number") control = Number(key, item, value);
            else if (kind == "key") control = KeyBox(key, Convert.ToString(value, CultureInfo.InvariantCulture) ?? "", typing);
            else if (kind == "pick") control = Pick(key, options, value);
            else if (kind == "voice") control = new Toggle(value != null && Convert.ToBoolean(value, CultureInfo.InvariantCulture));
            else control = Segments(key, options, value);
            if (kind == "voice")
            {
                bool on = ((Toggle)control).On;
                string group = Overlay.Str(item, "group"), voice = Overlay.Str(item, "voice");
                control.MouseLeftButtonUp += delegate { Tick(key, group, voice, on); };
            }
            string heard = kind == "voice" ? Overlay.Str(item, "voice") : item.ContainsKey("play") && Convert.ToBoolean(item["play"], CultureInfo.InvariantCulture) ? Convert.ToString(value, CultureInfo.InvariantCulture) : "";
            if (heard != null && heard.Length > 0)  // a voice: a button to hear it beside what sets it
            {
                var both = new StackPanel { Orientation = Orientation.Horizontal };
                var play = PlayButton(heard, item.ContainsKey("playing") && Convert.ToBoolean(item["playing"], CultureInfo.InvariantCulture));
                play.Margin = new Thickness(0, 0, 10, 0);
                if (kind == "pick") control.Width = 214;  // one width for every session's voice, so the buttons line up
                both.Children.Add(play);
                both.Children.Add(control);
                control.VerticalAlignment = VerticalAlignment.Center;
                control = both;
            }
            control.Margin = new Thickness(18, 0, 0, 0);
            control.VerticalAlignment = VerticalAlignment.Center;
            Grid.SetColumn(control, line.ColumnDefinitions.Count - 1);
            line.Children.Add(control);
            return line;
        }

        // A few choices side by side, the chosen one raised.
        FrameworkElement Segments(string key, object[] options, object value)
        {
            var row = new StackPanel { Orientation = Orientation.Horizontal };
            foreach (object o in options)
            {
                var pair = o as object[];
                if (pair == null || pair.Length < 2) continue;
                object mine = pair[0];
                bool on = Same(mine, value);
                var part = new Border { CornerRadius = new CornerRadius(6), Padding = new Thickness(11, 4, 11, 5), Cursor = Cursors.Hand };
                part.Child = new TextBlock { Text = Convert.ToString(pair[1], CultureInfo.InvariantCulture), FontSize = 12, FontWeight = on ? FontWeights.SemiBold : FontWeights.Normal, Foreground = on ? Brushes.White : Ui.Dim };
                if (on) part.Background = Ui.Paint("#3DFFFFFF");
                else
                {
                    Lit(part, "#00FFFFFF", "#1AFFFFFF");
                    part.MouseLeftButtonUp += delegate { choose(key, mine); };
                }
                row.Children.Add(part);
            }
            return new Border { CornerRadius = new CornerRadius(8), Background = Ui.Paint("#17FFFFFF"), Padding = new Thickness(2), Child = row };
        }

        FrameworkElement Number(string key, Dictionary<string, object> item, object value)
        {
            double min = Convert.ToDouble(item["min"], CultureInfo.InvariantCulture), max = Convert.ToDouble(item["max"], CultureInfo.InvariantCulture);
            double step = Convert.ToDouble(item["step"], CultureInfo.InvariantCulture);
            string unit = Overlay.Str(item, "unit");
            // "scale": the figure shown is the value times this, as 0.9 shown as 90%.
            double scale = item.ContainsKey("scale") ? Convert.ToDouble(item["scale"], CultureInfo.InvariantCulture) : 1;
            string places = step * scale >= 1 ? "0" : step * scale >= 0.1 ? "0.0" : "0.00";
            var slide = new Slide(min, max, step, value == null ? min : Convert.ToDouble(value, CultureInfo.InvariantCulture));
            var figure = new TextBlock { FontSize = 12, FontWeight = FontWeights.SemiBold, Foreground = Ui.Dim, Width = 46, TextAlignment = TextAlignment.Right, VerticalAlignment = VerticalAlignment.Center };
            figure.Text = (slide.Value * scale).ToString(places, CultureInfo.InvariantCulture) + unit;
            slide.Moved = delegate(double now)
            {
                figure.Text = (now * scale).ToString(places, CultureInfo.InvariantCulture) + unit;
                if (Previewing != null) Previewing(key, now);
            };
            slide.Chosen = delegate(double now) { choose(key, now); };
            var row = new StackPanel { Orientation = Orientation.Horizontal };
            row.Children.Add(slide);
            row.Children.Add(figure);
            return row;
        }

        // One key of a hotkey. Not amber like the keys of a request: nothing here asks for you.
        static Border Cap(string key)
        {
            return new Border {
                CornerRadius = new CornerRadius(4), BorderThickness = new Thickness(1), Padding = new Thickness(6, 1, 6, 2), Margin = new Thickness(0, 0, 4, 0), MinWidth = 22,
                BorderBrush = Ui.Paint("#52FFFFFF"), Background = Ui.Paint("#1FFFFFFF"),
                Child = new TextBlock { Text = key, FontSize = 11.5, FontWeight = FontWeights.SemiBold, HorizontalAlignment = HorizontalAlignment.Center },
            };
        }

        // A hotkey as its keys. A click on it waits for new ones.
        FrameworkElement KeyBox(string key, string combo, bool typing)
        {
            var box = new Border { CornerRadius = new CornerRadius(8), BorderThickness = new Thickness(1), Padding = new Thickness(7, 5, 3, 5), Cursor = Cursors.Hand, MinHeight = 32 };
            if (typing)
            {
                box.Background = Ui.Alpha(Accent, 0.16);
                box.BorderBrush = Ui.Alpha(Accent, 0.9);
                box.Padding = new Thickness(10, 5, 10, 5);
                box.Child = new TextBlock { Text = "Press the keys", FontSize = 12, FontWeight = FontWeights.SemiBold, VerticalAlignment = VerticalAlignment.Center };
            }
            else
            {
                box.BorderBrush = Ui.Paint("#00FFFFFF");
                Lit(box, "#00FFFFFF", "#14FFFFFF");
                if (combo.Trim().Length == 0)
                {
                    box.Padding = new Thickness(10, 5, 10, 5);
                    box.Child = new TextBlock { Text = "No key", FontSize = 12, Foreground = Ui.Faint, VerticalAlignment = VerticalAlignment.Center };
                }
                else
                {
                    var caps = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center };
                    foreach (string part in combo.Split('+')) if (part.Trim().Length > 0) caps.Children.Add(Cap(part.Trim()));
                    box.Child = caps;
                }
            }
            box.MouseLeftButtonUp += delegate
            {
                bool start = capturing != key;
                capturing = start ? key : "";
                typingKey(start);
                Fill();
                Window.Activate();
                Window.Focus();
            };
            return box;
        }

        // One of many: what is chosen, and a list that drops down from it.
        FrameworkElement Pick(string key, object[] options, object value)
        {
            string shown = Convert.ToString(value, CultureInfo.InvariantCulture) ?? "";
            var menu = new StackPanel();
            var popup = new System.Windows.Controls.Primitives.Popup { Placement = System.Windows.Controls.Primitives.PlacementMode.Bottom, StaysOpen = false, AllowsTransparency = true, VerticalOffset = 4 };
            foreach (object o in options)
            {
                var pair = o as object[];
                if (pair == null || pair.Length < 2) continue;
                object mine = pair[0];
                bool on = Same(mine, value);
                if (on) shown = Convert.ToString(pair[1], CultureInfo.InvariantCulture);
                var entry = new Border { CornerRadius = new CornerRadius(5), Padding = new Thickness(10, 4, 10, 5), Cursor = Cursors.Hand };
                entry.Child = new TextBlock { Text = Convert.ToString(pair[1], CultureInfo.InvariantCulture), FontSize = 12, FontWeight = on ? FontWeights.SemiBold : FontWeights.Normal, Foreground = on ? Brushes.White : Ui.Dim };
                Lit(entry, on ? "#2EFFFFFF" : "#00FFFFFF", "#24FFFFFF");
                entry.MouseLeftButtonUp += delegate { popup.IsOpen = false; if (!on) choose(key, mine); };
                menu.Children.Add(entry);
            }
            popup.Child = new Border {
                CornerRadius = new CornerRadius(9), Background = Ui.Paint("#FA20242C"), BorderBrush = Ui.Paint("#38FFFFFF"), BorderThickness = new Thickness(1), Padding = new Thickness(4), MinWidth = 160,
                Child = new ScrollViewer { MaxHeight = 264, VerticalScrollBarVisibility = ScrollBarVisibility.Hidden, Focusable = false, Content = menu },
            };
            var face = new Grid();
            face.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            face.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            face.Children.Add(new TextBlock { Text = shown, FontSize = 12, VerticalAlignment = VerticalAlignment.Center });
            var arrow = new System.Windows.Shapes.Path { Data = Geometry.Parse("M0,0 L4,4 L8,0"), Stroke = Ui.Dim, StrokeThickness = 1.4, StrokeStartLineCap = PenLineCap.Round, StrokeEndLineCap = PenLineCap.Round, StrokeLineJoin = PenLineJoin.Round, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(10, 2, 0, 0) };
            Grid.SetColumn(arrow, 1);
            face.Children.Add(arrow);
            var box = new Border { CornerRadius = new CornerRadius(8), BorderBrush = Ui.Paint("#24FFFFFF"), BorderThickness = new Thickness(1), Padding = new Thickness(11, 5, 10, 6), MinWidth = 160, Cursor = Cursors.Hand, Child = face };
            Lit(box, "#17FFFFFF", "#26FFFFFF");
            popup.PlacementTarget = box;
            // A second click on the box closes the list (the author, 2026-11-20: "if I click again the
            // select shouldn't it be closing"). The list already shuts on the press of that click, as
            // any click outside it does, so the release must not open it again.
            DateTime shut = DateTime.MinValue;
            popup.Closed += delegate { shut = DateTime.UtcNow; };
            box.MouseLeftButtonUp += delegate
            {
                if (popup.IsOpen) popup.IsOpen = false;
                else if ((DateTime.UtcNow - shut).TotalMilliseconds > 400) popup.IsOpen = true;
            };
            return box;
        }

        // Esc closes the window. While a hotkey is being typed every key is for that: the keys
        // held and one more make the new hotkey.
        void OnKey(object sender, KeyEventArgs e)
        {
            Key key = e.Key == Key.System ? e.SystemKey : e.Key;
            if (capturing.Length == 0)
            {
                if (key == Key.Escape) { Close(); e.Handled = true; }
                return;
            }
            e.Handled = true;
            if (key == Key.LeftCtrl || key == Key.RightCtrl || key == Key.LeftAlt || key == Key.RightAlt || key == Key.LeftShift
                || key == Key.RightShift || key == Key.LWin || key == Key.RWin || key == Key.None || key == Key.ImeProcessed) return;
            ModifierKeys held = Keyboard.Modifiers;
            if (key == Key.Escape && held == ModifierKeys.None) { StopTyping(); return; }
            string combo = "";
            if (!(key == Key.Delete && held == ModifierKeys.None))
            {
                // A key by itself would be taken from every program while you type; the F keys are the exception.
                if (held == ModifierKeys.None && !(key >= Key.F1 && key <= Key.F24)) return;
                if ((held & ModifierKeys.Control) != 0) combo += "Ctrl+";
                if ((held & ModifierKeys.Alt) != 0) combo += "Alt+";
                if ((held & ModifierKeys.Shift) != 0) combo += "Shift+";
                if ((held & ModifierKeys.Windows) != 0) combo += "Win+";
                combo += new KeyConverter().ConvertToInvariantString(key);
            }
            string which = capturing;
            capturing = "";
            typingKey(false);
            choose(which, combo);
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
        // While sessions are being reordered: how far the light is moved along the bar (the one
        // held follows the mouse, the others make room). The one held keeps its size (the
        // author did not like it growing).
        public readonly TranslateTransform Shift = new TranslateTransform();
        public readonly TranslateTransform TextShift = new TranslateTransform();  // its row, level with it in the bar layout
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
        public string Doing { get { return rowText; } }  // what its line under the name says when nothing is being said
        public object[] Details = new object[0];  // its figures for the line under the rows: [what it is, the figure] each

        public Row(bool right, Wave wave)
        {
            Wave = Orb.Wave = Strip.Wave = wave;
            Strip.NewestRight = right;
            Light.Children.Add(Orb);
            Light.Children.Add(Pip);
            Light.RenderTransform = Shift;
            Text.RenderTransform = TextShift;
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
            int waits = s.ContainsKey("waiting") ? (int)Convert.ToDouble(s["waiting"], CultureInfo.InvariantCulture) : 0;
            if (waits > Orb.Waiting)  // another message joined: the number shows itself again
            {
                Orb.WaitingSince = Ui.Now;
                Orb.Covers = Ui.WaitingCover == "each" || (Ui.WaitingCover == "first" && Orb.Waiting == 0);
            }
            Orb.Waiting = waits;
            Orb.SetContext(s.ContainsKey("context") && s["context"] != null ? Convert.ToDouble(s["context"], CultureInfo.InvariantCulture) : -1);
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
            Details = s.ContainsKey("details") && s["details"] is object[] ? (object[])s["details"] : new object[0];
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
            Strip.Tint = Orb.Listening != null ? Ui.MicLine : Ui.Tint(State);
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
        const int WH_KEYBOARD_LL = 13, WM_KEYDOWN = 0x0100, WM_SYSKEYDOWN = 0x0104, WM_KEYUP = 0x0101, WM_SYSKEYUP = 0x0105;
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
        // While the voice is off, a small piece of glass with a struck-out speaker just past the far
        // end of the bar (overlay.muted_mark, off: the author did not like it there and chose a
        // line in the details, muted_line). A window of its own, so the lights and rows stay put.
        readonly Glass muteChip = new Glass(0);
        const double ChipSize = 32, ChipGap = 4;
        bool muted, mutedMark;
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
        int[] dragKeys = new int[0];  // "": a plain drag moves the bar
        string dragKeysName = "";
        int[] reorderKeys = { VK_CONTROL, VK_MENU };  // held while a light is dragged: it goes to another place in the bar
        Row lifted;  // the light being dragged to another place, while `dragging`
        double liftGrab;  // where along the bar it was taken hold of, in the bar's units
        bool undecided;  // pressed, and not moved far enough yet to say whether a light or the bar is dragged
        double pressAlong;
        double reorderHeldAt = -1;  // when the reorder keys were last seen held, over the bar
        int wheelTurned;
        double wheelUntil, selectorY, selectorShown, heldSince;
        bool wheeling, keysOpen;
        readonly Grid spare = new Grid { Width = Row.High, Height = Row.High };  // a dim light shown when there is no session
        readonly StackPanel sections = new StackPanel { Margin = new Thickness(3) };
        readonly StackPanel rowsPanel = new StackPanel();
        readonly StackPanel requestBox = new StackPanel(), bannerBox = new StackPanel(), historyBox = new StackPanel();
        // "Voice is muted" in the details while the voice is off (overlay.muted_line): the author
        // wanted it there rather than as a mark past the bar.
        readonly StackPanel mutedBox = new StackPanel();
        readonly TextBlock mutedText = new TextBlock();
        bool mutedLine = true;
        readonly StackPanel historyLines = new StackPanel();
        // The figures of one session, each with its name in front, under the rows: the session
        // the mouse is on, else the one in focus. The hub says which figures (`details` of a row).
        readonly TextBlock metricsLine = new TextBlock { FontSize = 12, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 1, 0, 2) };
        // The same as a card (details_style "tiles", the default): one tile for each figure, its
        // name small above it, the figure large, and under it a thin bar where the figure is a
        // share of a whole. Every figure keeps its place whether it is known or not, so the eye
        // learns where each one is.
        readonly Border metricsCard = new Border { CornerRadius = new CornerRadius(8), Background = Ui.Paint("#12FFFFFF"), Padding = new Thickness(11, 7, 11, 12), Margin = new Thickness(-3, 2, -3, -3) };
        readonly StackPanel metricsBody = new StackPanel();
        // While the voice is off, a struck-out speaker in the card's top right corner (the
        // author's idea, overlay.muted_icon), laid over the card so nothing in it moves.
        readonly MutedSpeaker mutedIcon = new MutedSpeaker(17)
        {
            HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Top,
            Margin = new Thickness(0, 0, -2, 0), Visibility = Visibility.Collapsed,
        };
        bool mutedIconOn = true, mutedCardIcon;  // the bubble's; the card's (taken out again on the author's word)
        // ... and in the top right of the bubble that pops out beside a light when a session's
        // line comes (the author keeps the details away, so that is where they look).
        readonly MutedSpeaker bubbleMuted = new MutedSpeaker(16) { Margin = new Thickness(8, 1, 0, 0), VerticalAlignment = VerticalAlignment.Top, Visibility = Visibility.Collapsed };
        string detailsStyle = "tiles";
        bool detailsBars;  // a thin bar under a tile's figure where it is a share of a whole
        bool choiceCaps;  // the number in front of a question's choice drawn as a key cap, not as a plain number
        readonly TextBlock requestTitle = new TextBlock(), requestDetail = new TextBlock(), requestKeys = new TextBlock();
        // What the keys do, each key drawn as a small cap: quicker to take in than a line of text.
        readonly WrapPanel requestCaps = new WrapPanel { Margin = new Thickness(0, 2, 0, 0) };
        // The choices of a question, one row each, and how many more requests wait behind this one.
        readonly StackPanel requestChoices = new StackPanel { Margin = new Thickness(0, 4, 0, 4), MaxHeight = 190, ClipToBounds = true };
        readonly TextBlock requestMore = new TextBlock { Foreground = Ui.Faint, FontSize = 12 };
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
        bool shareTaken = true;  // overlay.share_taken_keys
        // Hotkeys another program had reserved first: name -> key and MOD_ flags. The keyboard hook
        // watches for them and lets them through, so the other program acts on them as well.
        readonly Dictionary<string, uint[]> shared = new Dictionary<string, uint[]>();
        readonly HashSet<uint> sharedDown = new HashSet<uint>();  // so a held key acts once, not on every repeat
        readonly HashSet<int> masked = new HashSet<int>();  // those keys: still held as far as we know, though Windows was told they are up
        double maskedUntil;  // once talking is over, how long we go on believing that without a sign of it
        const double MaskGrace = 3;
        const long Ours = 0x43535031;  // marks the key events the overlay sends itself
        readonly Dictionary<string, uint[]> claims = new Dictionary<string, uint[]>();  // hotkey name -> its key and MOD_ flags
        readonly IntPtr hwnd;
        SettingsWindow settings;  // made when it is first asked for
        bool typingKey;  // a hotkey is being typed into the settings: our own hotkeys are let go meanwhile

        object[] sessions = new object[0];
        object[] history = new object[0];
        bool usageRows = true;  // each bar of the plan's usage on a line of its own (`usage_layout`)
        bool historyAll;  // the history shows every session's lines, not only those of the one under the mouse
        // The mouse alone on the bar brings the details out. `hover: keys` turns that off, for a
        // bar that must not answer to a mouse passing over it in a game: then only holding
        // Ctrl+Alt brings them out. The author asked for that as the default, tried to picture
        // it and took it back ("I like hovering ... opening up its details"), so it is a choice.
        bool hoverOpens = true;
        // With the details kept out (the list key), a drag on them moves the whole overlay, and
        // the panel goes along instead of folding away; a click on them still goes to what is
        // behind. The author, 2026-11-19: "if it's fully displayed with Ctrl+Alt+L, I should be
        // able to move the entire overlay" (only the narrow bar of lights could be grabbed).
        bool panelDrag = true;
        bool panelHeld, panelCatching;
        object[] usage = new object[0];  // the plan's usage, from the hub: [what, percent, "warn" or ""] each
        string focusWas = "";  // the session in focus as of the last state, to notice when it moves
        string historyOf = "";  // the session whose lines the history shows: the one the mouse was on last
        int historyTicks = 3;  // looks of 30 ms the mouse rests on the details before the history shows (`history_after`)
        int monitor, insideTicks, outsideTicks;  // monitor: 0 = primary, 1.. = the others in Windows' order
        bool moving, dragging, catching, hover, peek, peekForced, opaque, hasRequest, hasBanner, running, still;
        string mode = "dots", restMode = "dots", corner = "top-right", glass = "blur", bubbleShows = "";
        double offsetX = 12, offsetY = 96, idleOpacity = 1.0, listOpacity = 1.0, lastFade = -1;
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
        bool talkQuiet;  // the step is news from the hub, not something you are doing: it leaves the bubble to a session that is speaking
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
            muteChip.Panel.Child = new Border { Width = ChipSize - 2, Height = ChipSize - 2, Child = new MutedSpeaker(18) };
            wheelProc = OnMouse;  // kept in a field so it stays alive while Windows holds it
            keyProc = OnKey;
            rail.MouseWheel += delegate(object sender, MouseWheelEventArgs e) { Wheel(e.Delta); };
            rail.Cursor = Cursors.Arrow;

            requestTitle.TextWrapping = requestKeys.TextWrapping = requestDetail.TextWrapping = TextWrapping.Wrap;
            requestTitle.MaxHeight = 54;
            requestTitle.TextTrimming = requestDetail.TextTrimming = TextTrimming.CharacterEllipsis;
            requestDetail.FontFamily = requestMono;
            requestDetail.Foreground = Ui.Dim;
            requestDetail.Margin = new Thickness(0, 4, 0, 4);
            requestKeys.Foreground = Ui.AmberEdge;
            Section(requestBox, requestTitle, requestDetail, requestChoices, requestKeys, requestCaps, requestMore);
            bannerTitle.TextWrapping = bannerHint.TextWrapping = TextWrapping.Wrap;
            bannerHint.Foreground = Ui.Faint;
            bannerHint.Margin = new Thickness(0, 2, 0, 0);
            Section(bannerBox, bannerTitle, bannerHint);
            Section(mutedBox, mutedText);
            var cardLayers = new Grid();
            cardLayers.Children.Add(metricsBody);
            cardLayers.Children.Add(mutedIcon);
            metricsCard.Child = cardLayers;
            Section(historyBox, metricsLine, metricsCard, historyLines);
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
            bubbleRow1.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            Grid.SetColumn(bubbleBadge, 1);
            Grid.SetColumn(bubbleMuted, 2);
            bubbleRow1.Children.Add(bubbleLine1);
            bubbleRow1.Children.Add(bubbleBadge);
            bubbleRow1.Children.Add(bubbleMuted);
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
            rail.MouseLeftButtonDown += delegate(object sender, MouseButtonEventArgs e) { Press(e.GetPosition(rail)); };
            panel.MouseLeftButtonDown += delegate(object sender, MouseButtonEventArgs e) { PressPanel(e.GetPosition(panel)); };
            // Hold-to-talk: a hotkey only reports the press, so watch the key until it comes back up.
            holdTimer.Interval = TimeSpan.FromMilliseconds(30);
            holdTimer.Tick += delegate { if (!Down((int)heldKey)) EndHold(); };
            // Other always-on-top windows (and some games) push us down; climb back regularly.
            topTimer.Interval = TimeSpan.FromSeconds(2);
            topTimer.Tick += delegate { rail.Raise(); panel.Raise(); bubble.Raise(); muteChip.Raise(); };

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
            overlay.HoldKey(0);  // the hub is gone: no key stays held by us
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
                    if (msg.ContainsKey("waiting_color")) Ui.SetWaitingColor(Str(msg, "waiting_color"));
                    if (msg.ContainsKey("mic_color")) Ui.Mic = Ui.ColorOr(Str(msg, "mic_color"), Ui.Mic);
                    if (msg.ContainsKey("details_style")) detailsStyle = Str(msg, "details_style") == "line" ? "line" : "tiles";
                    if (msg.ContainsKey("details_bars")) detailsBars = Convert.ToBoolean(msg["details_bars"]);
                    if (msg.ContainsKey("choice_caps")) choiceCaps = Convert.ToBoolean(msg["choice_caps"]);
                    Ui.ContextWarn = Num(msg, "context_warn", Ui.ContextWarn);
                    if (msg.ContainsKey("context_color")) Ui.Context = Ui.ColorOr(Str(msg, "context_color"), Colors.White);
                    if (msg.ContainsKey("context_warn_color")) Ui.ContextFull = Ui.ColorOr(Str(msg, "context_warn_color"), Ui.ContextFull);
                    Ui.WaitingHold = Math.Max(0, Num(msg, "waiting_hold", Ui.WaitingHold));
                    Ui.WaitingSize = Math.Max(5, Math.Min(13, Num(msg, "waiting_size", Ui.WaitingSize)));
                    if (msg.ContainsKey("waiting_many")) Ui.WaitingMany = Str(msg, "waiting_many") == "number" ? "number" : "face";
                    if (msg.ContainsKey("waiting_cover"))
                    {
                        string cover = Str(msg, "waiting_cover");
                        Ui.WaitingCover = cover == "each" || cover == "first" ? cover : "never";
                    }
                    if (msg.ContainsKey("waiting_mark"))
                    {
                        string mark = Str(msg, "waiting_mark");
                        Ui.WaitingMark = mark == "dot" || mark == "clock" ? mark : "number";
                    }
                    glass = Str(msg, "glass", glass);
                    Ui.GlassClear = Num(msg, "glass_clear", Ui.GlassClear);
                    islandX = Num(msg, "island_x", islandX);
                    islandY = Num(msg, "island_y", islandY);
                    string wanted = Str(msg, "layout", layout);
                    if (wanted != "island") wanted = "bar";
                    if (wanted != layout) { layout = wanted; ApplyLayout(); RegisterHotkeys(); }  // other arrow keys now
                    if (msg.ContainsKey("focus_wheel")) wheelKeys = Keys(Str(msg, "focus_wheel"));
                    if (msg.ContainsKey("drag_keys")) { dragKeys = Keys(Str(msg, "drag_keys")); dragKeysName = Str(msg, "drag_keys"); }
                    if (msg.ContainsKey("reorder_keys")) reorderKeys = Keys(Str(msg, "reorder_keys"));
                    Ui.RowLines = Math.Max(1, Math.Min(3, (int)Num(msg, "row_lines", Ui.RowLines)));
                    if (msg.ContainsKey("talk_sign")) Ui.SignInLight = Str(msg, "talk_sign") != "line";
                    keepTalk = Str(msg, "keep_talk_key", keepTalk);
                    if (msg.ContainsKey("history")) historyAll = Str(msg, "history") == "all";
                    if (msg.ContainsKey("usage_layout")) usageRows = Str(msg, "usage_layout") != "line";
                    historyTicks = (int)Math.Max(1, Math.Round(Num(msg, "history_after", historyTicks * 0.03) / 0.03));
                    if (msg.ContainsKey("hover")) hoverOpens = Str(msg, "hover") != "keys";
                    if (msg.ContainsKey("panel_drag")) panelDrag = Convert.ToBoolean(msg["panel_drag"]);
                    if (msg.ContainsKey("resize")) Glass.Resize = Str(msg, "resize", "quick");
                    if (msg.ContainsKey("talk_frees_keys")) freeKeys = Convert.ToBoolean(msg["talk_frees_keys"]);
                    if (msg.ContainsKey("share_taken_keys")) shareTaken = Convert.ToBoolean(msg["share_taken_keys"]);
                    if (msg.ContainsKey("muted_mark")) mutedMark = Convert.ToBoolean(msg["muted_mark"]);
                    if (msg.ContainsKey("muted_line")) mutedLine = Convert.ToBoolean(msg["muted_line"]);
                    if (msg.ContainsKey("muted_icon")) mutedIconOn = Convert.ToBoolean(msg["muted_icon"]);
                    if (msg.ContainsKey("muted_card_icon")) mutedCardIcon = Convert.ToBoolean(msg["muted_card_icon"]);
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
                    usage = msg.ContainsKey("usage") && msg["usage"] is object[] ? (object[])msg["usage"] : new object[0];
                    muted = msg.ContainsKey("muted") && Convert.ToBoolean(msg["muted"]);
                    // The focus moved to another session (arrows, wheel, another terminal, or it
                    // spoke): the card and the history are about that one now, not about the one
                    // the mouse was on last. A mouse that is on a row right now still has its say.
                    string inFocus = "";
                    foreach (object o in sessions)
                    {
                        var row = (Dictionary<string, object>)o;
                        if (row.ContainsKey("target") && Convert.ToBoolean(row["target"])) inFocus = Str(row, "name");
                    }
                    if (inFocus != focusWas) { focusWas = inFocus; if (inFocus.Length > 0) historyOf = inFocus; }
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
                case "settings":  // the settings window: open with what there is to set, or closed
                    // "toggle" (the key): shut it if it is in front of you, else bring it there. Only
                    // the window knows which, now that it can lie behind other programs.
                    if (msg.ContainsKey("toggle") && Convert.ToBoolean(msg["toggle"]) && settings != null && settings.InFront)
                    {
                        settings.Hide();
                        Write(new Dictionary<string, object> { { "type", "settings" }, { "open", false } });
                    }
                    else if (msg.ContainsKey("open") && Convert.ToBoolean(msg["open"]))
                    {
                        if (settings == null)
                        {
                            settings = new SettingsWindow(
                                delegate(string key, object value) { Write(new Dictionary<string, object> { { "type", "setting" }, { "key", key }, { "value", value } }); },
                                delegate { Write(new Dictionary<string, object> { { "type", "settings" }, { "open", false } }); },
                                delegate(bool typing) { typingKey = typing; RegisterHotkeys(); });
                            settings.Previewing = delegate(string key, double value)
                            {
                                if (key == "overlay.glass_clear") { Ui.GlassClear = value; SetGlass(); }
                            };
                            settings.Look(opaque ? "solid" : glass);
                        }
                        settings.Show(msg.ContainsKey("sections") && msg["sections"] is object[] ? (object[])msg["sections"] : new object[0], Str(msg, "section"), WorkArea(), msg.ContainsKey("quiet") && Convert.ToBoolean(msg["quiet"]), Str(msg, "title"));
                    }
                    else if (settings != null) settings.Hide();
                    if (settings != null && msg.ContainsKey("click") && msg["click"] is object[])
                    {
                        var at = (object[])msg["click"];
                        settings.Click(Convert.ToDouble(at[0], CultureInfo.InvariantCulture), Convert.ToDouble(at[1], CultureInfo.InvariantCulture));
                    }
                    break;
                case "logo":  // the tool's mark, written to a file as a picture
                    try { Logo.Save(Str(msg, "path"), (int)Num(msg, "size", 256), msg.ContainsKey("tile") && Convert.ToBoolean(msg["tile"])); Send("logo", "saved", Str(msg, "path")); }
                    catch (Exception e) { Error("logo not saved: " + e.Message); }
                    break;
                case "hold_key":  // held down while you talk, for another program's push-to-mute; "" lets go
                    uint held = 0;
                    string keyName = Str(msg, "key", "");
                    if (keyName.Length > 0)
                        try { held = (uint)KeyInterop.VirtualKeyFromKey((Key)new KeyConverter().ConvertFromInvariantString(keyName)); }
                        catch (Exception) { Error("key to hold not understood: " + keyName); }
                    HoldKey(held);
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
            string kind = opaque ? "solid" : Ui.GlassClear <= 0 ? "none" : glass;
            rail.Look(kind);
            panel.Look(kind);
            bubble.Look(kind);
            muteChip.Look(kind);
            if (settings != null) settings.Look(kind);
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
            if (panelCatching) { panelCatching = false; panel.CatchMouse(false); }
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
            var parts = new List<UIElement> { rowsPanel, emptyLine, mutedBox, requestBox, bannerBox, historyBox };
            if (bottom) parts.Reverse();
            sections.Children.Clear();
            foreach (UIElement part in parts) sections.Children.Add(part);
            foreach (StackPanel box in new[] { mutedBox, requestBox, bannerBox, historyBox })
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
        bool IsOpen() { return (!BarHeld || panelHeld) && (mode == "list" || hover || moving || hasRequest || hasBanner || keysOpen || Ui.Now < wheelUntil); }

        // Brings everything in line with what there is to show. What moves is then moved by Frame.
        void Render()
        {
            bool isList = mode == "list", open = IsOpen();
            SyncRows();
            requestBox.Visibility = hasRequest ? Visibility.Visible : Visibility.Collapsed;
            bannerBox.Visibility = hasBanner ? Visibility.Visible : Visibility.Collapsed;
            emptyLine.Visibility = sessions.Length == 0 ? Visibility.Visible : Visibility.Collapsed;
            bool showHistory = isList && peek && history.Length > 0;
            historyLines.Children.Clear();
            // The figures show whenever the details were asked for (not when the panel is only
            // out for a request or to be moved); the history, as before, in list mode at rest.
            bool asked = !BarHeld && !moving && (isList || hover || keysOpen || Ui.Now < wheelUntil);
            // One session's lines go into its card, under its figures. All sessions' lines mixed
            // (history "all"), or lines with no card to go into, stand below it as before.
            bool inCard = showHistory && detailsStyle != "line" && !historyAll;
            bool showMetrics = asked && BuildMetrics(inCard);
            if (showHistory && !(inCard && showMetrics)) BuildHistory();
            metricsCard.Padding = new Thickness(11, 7, 11, usage.Length == 0 && inCard && showMetrics && metricsBody.Children.Count > 2 ? 8 : 11);
            metricsLine.Visibility = showMetrics && detailsStyle == "line" ? Visibility.Visible : Visibility.Collapsed;
            metricsCard.Visibility = showMetrics && detailsStyle != "line" ? Visibility.Visible : Visibility.Collapsed;
            if (metricsCard.Visibility != Visibility.Visible) { stood.Clear(); gliding.Clear(); }  // the bars fill from nothing when it comes up again
            // The same room above the card as below it (10 px), whichever of the two is the
            // panel's edge and whichever the dividing line; more when the history follows.
            bool linesFollow = historyLines.Children.Count > 0;
            metricsCard.Margin = Low ? new Thickness(-3, -1, -3, linesFollow ? 6 : 1) : new Thickness(-3, 2, -3, linesFollow ? 6 : -3);
            historyBox.Visibility = showMetrics || historyLines.Children.Count > 0 ? Visibility.Visible : Visibility.Collapsed;
            mutedIcon.Visibility = muted && mutedCardIcon ? Visibility.Visible : Visibility.Collapsed;
            if (muted && mutedLine && asked && !hasBanner)  // with the details, and not twice while "Voice off" is up
            {
                string key;
                VoiceRow(mutedText, true, "Voice is muted",
                         wantedKeys.TryGetValue("mute", out key) && key.Trim().Length > 0 ? key + " turns it on" : "");
                mutedBox.Visibility = Visibility.Visible;
            }
            else mutedBox.Visibility = Visibility.Collapsed;
            bool talking = talkState.Length > 0;
            foreach (Row row in order)
                if (talking && row.Name == talkName) row.SetTalk(TalkKind(), TalkWords(), TalkInk(), talkState == "listening" ? mic : null);
                else row.SetTalk(null, "", Brushes.White, null);
            bool show = isList || hasRequest || hasBanner || moving || talking || sessions.Length > 0;
            if (show && !rail.IsVisible) rail.Show();
            else if (!show && rail.IsVisible) rail.Hide();
            ShowMuteChip();

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
            bool talking = talkState.Length > 0, away = !IsOpen() && barShown && !BarHeld;
            // Words that waited and are now handed over show as a sign on their session's light.
            // They do not take the bubble from a line that is being said: it jumped to the other
            // session and back in the middle of a sentence.
            bool hushed = false;
            if (talking && talkQuiet)
                foreach (Row row in order) if (row.Speaking) hushed = true;
            if (hushed) talking = false;
            if (away)
                foreach (Row row in order)
                {
                    if (row.TalkKind != null && !hushed) { found = row; break; }  // what you are saying comes first
                    if (row.Saying && (found == null || row.Speaking || (!found.Speaking && row.FlashUntil > found.FlashUntil))) found = row;
                }
            bool orphan = away && talking && (found == null || found.TalkKind == null);  // push-to-talk with no session to show it on
            // Details "Selected Only": with nothing being said, the bubble shows the session in focus,
            // its name, title and line, three lines at most, and the other lights show nothing (the
            // author, 2026-11-21: "just the session squares on the bar ... and in the detail just
            // show the details of the session selected").
            bool resting = false;
            if (found == null && !orphan && away && mode == "focus")
                foreach (Row row in order) if (row.Focus || (found == null && order.Count == 1)) { found = row; resting = true; }
            if (found == null && !orphan) { bubble.Goal = 0; return; }
            talker = orphan ? null : found;
            // The first line is always the session's name and title; push-to-talk shows as a sign
            // at its right and as words underneath.
            bool mine = orphan || (found.TalkKind != null && !hushed), listening = mine && talkState == "listening";
            string head = orphan ? TalkWords() : found.Name, sub = orphan ? "" : found.Title, body = orphan ? "" : mine ? TalkWords() : resting ? found.Doing : found.FlashText;
            bubbleLine2.MaxHeight = resting ? 51 : 68;  // three lines for the one in focus, four while one is said
            string kind = mine ? TalkKind() : "";
            bubbleMuted.Visibility = muted && mutedIconOn && !mine ? Visibility.Visible : Visibility.Collapsed;  // a line shown, not said
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
                bubbleStrip.Tint = mine ? Ui.MicLine : Ui.Tint(found.State);
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
            bool found = false, held = false;
            foreach (Row row in order)
            {
                double room = Island ? Row.High : row.Light.Height;
                if (row.Focus)
                {
                    // Where the light is drawn, not only its place: while sessions are being
                    // reordered it is held, or making room, and the frame goes with it.
                    goal = at + (room - selector.Height) / 2 + (Island ? row.Shift.X : row.Shift.Y);
                    found = true;
                    held = row == lifted;
                    break;
                }
                at += room;
            }
            if (found && (selectorShown < 0.02 || held)) selectorY = goal;  // in place instead of flying in; on the light held, no lag behind it
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
        // Writes the line of figures for the session the mouse is on (it stays chosen when the
        // mouse moves off, like the history), else the one in focus, else the only one. False
        // when there is nothing to say.
        // Where the bar in each place of the card stood when it was last drawn (0 when the card
        // was away), so that a bar can glide from there; and notes where it stands now. The
        // card is drawn anew whenever anything changes, also in the middle of a glide: then
        // the bar goes on from where the glide had got to, not from its end.
        readonly Dictionary<string, double> stood = new Dictionary<string, double>();
        readonly Dictionary<string, double[]> gliding = new Dictionary<string, double[]>();  // place -> from, to, since when
        const double GlideTakes = 0.34;

        double Stood(string place, double now)
        {
            double was = stood.ContainsKey(place) ? stood[place] : 0;
            if (gliding.ContainsKey(place))
            {
                double[] g = gliding[place];
                double done = (Ui.Now - g[2]) / GlideTakes;
                if (done < 1) was = g[0] + (g[1] - g[0]) * Ui.EaseOut(done);
                else gliding.Remove(place);
            }
            if (Math.Abs(was - now) > 0.005) gliding[place] = new[] { was, now, Ui.Now };
            stood[place] = now;
            return was;
        }

        bool BuildMetrics(bool withLines)
        {
            // Whichever was chosen last: the row the mouse went onto, or the session the focus
            // moved to (`historyOf` is set by both). Before either, the session in focus.
            Row about = null;
            foreach (Row row in order) if (row.Name == historyOf) about = row;
            if (about == null) about = hot;
            if (about == null) foreach (Row row in order) if (row.Focus) about = row;
            if (about == null && order.Count == 1) about = order[0];
            metricsLine.Inlines.Clear();
            metricsBody.Children.Clear();
            if (about == null) return false;
            // Each tile keeps 12 px to its right as the gap to the next; the last one's is taken
            // back, so that the card has the same room on both sides.
            var tiles = new System.Windows.Controls.Primitives.UniformGrid { Rows = 1, Margin = new Thickness(0, 0, -12, 0) };
            bool any = false;
            foreach (object o in about.Details)
            {
                var part = o as object[];
                if (part == null || part.Length < 2) continue;
                string name = Convert.ToString(part[0], CultureInfo.InvariantCulture), figure = Convert.ToString(part[1], CultureInfo.InvariantCulture);
                double share = part.Length > 2 && part[2] != null ? Ui.Clamp(Convert.ToDouble(part[2], CultureInfo.InvariantCulture)) : -1;
                bool warn = part.Length > 3 && Convert.ToString(part[3], CultureInfo.InvariantCulture) == "warn";
                any |= figure.Length > 0;
                if (figure.Length > 0)
                {
                    if (metricsLine.Inlines.Count > 0) metricsLine.Inlines.Add(new Run("     "));
                    metricsLine.Inlines.Add(new Run(name + " ") { Foreground = Ui.Faint });
                    metricsLine.Inlines.Add(new Run(figure) { Foreground = Brushes.White });
                }
                tiles.Children.Add(Tile(name, figure, detailsBars ? share : -2, warn, detailsBars && share >= 0 ? Stood("tile" + tiles.Children.Count, share) : -1));
            }
            if (!any) return false;
            if (order.Count > 1)  // whose figures they are, where there is a choice
            {
                var whose = new TextBlock { FontSize = 12, Margin = new Thickness(0, 0, 0, 5), TextTrimming = TextTrimming.CharacterEllipsis };
                Heading(whose, about.Name, about.Title, about.Color);
                metricsBody.Children.Add(whose);
            }
            metricsBody.Children.Add(tiles);
            if (withLines)  // what it said last, in the same card, under a faint line
            {
                var said = new StackPanel();
                FillHistory(said, about.Name, 4, false);
                if (said.Children.Count > 0)
                {
                    metricsBody.Children.Add(new Border { Height = 1, Background = Ui.Paint("#22FFFFFF"), Margin = new Thickness(0, 10, 0, 6) });
                    metricsBody.Children.Add(said);
                }
            }
            if (usage.Length > 0)  // the plan's usage, which is nobody's in particular: at the foot, under a faint line
            {
                metricsBody.Children.Add(new Border { Height = 1, Background = Ui.Paint("#22FFFFFF"), Margin = new Thickness(0, 9, 0, 7) });
                // Each has a line of its own, the names in one column and the bars one length, so
                // they can be compared. `usage_layout: line` puts two side by side; three (with
                // the week of one model) never share a line: that left each bar some 25 px.
                bool stacked = usage.Length > 2 || usageRows;
                Panel plan = stacked ? (Panel)new Grid() : new System.Windows.Controls.Primitives.UniformGrid { Rows = 1, Margin = new Thickness(0, 0, -14, 0) };
                if (stacked) Grid.SetIsSharedSizeScope(plan, true);
                foreach (object o in usage)
                {
                    var part = o as object[];
                    if (part == null || part.Length < 2) continue;
                    double used = Ui.Clamp(Convert.ToDouble(part[1], CultureInfo.InvariantCulture) / 100);
                    bool warn = part.Length > 2 && Convert.ToString(part[2], CultureInfo.InvariantCulture) == "warn";
                    var cell = new Grid { Margin = stacked ? new Thickness(0, plan.Children.Count > 0 ? 5 : 0, 0, 0) : new Thickness(0, 0, 14, 0) };
                    cell.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto, SharedSizeGroup = stacked ? "planName" : null });
                    cell.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                    cell.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto, SharedSizeGroup = stacked ? "planFigure" : null });
                    cell.Children.Add(new TextBlock { Text = Convert.ToString(part[0], CultureInfo.InvariantCulture), FontSize = 10.5, Foreground = Ui.Faint, VerticalAlignment = VerticalAlignment.Center });
                    UIElement bar = Meter(used, warn, Stood("plan" + plan.Children.Count, used), new Thickness(stacked ? 9 : 7, 1, stacked ? 9 : 7, 0));
                    Grid.SetColumn(bar, 1);
                    cell.Children.Add(bar);
                    var figure = new TextBlock { Text = Math.Round(used * 100) + "%", FontSize = 11.5, FontWeight = FontWeights.SemiBold, Foreground = warn ? Ui.Alpha(Ui.ContextFull, 1) : Ui.Dim, VerticalAlignment = VerticalAlignment.Center, HorizontalAlignment = HorizontalAlignment.Right };
                    Grid.SetColumn(figure, 2);
                    cell.Children.Add(figure);
                    if (stacked) { ((Grid)plan).RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto }); Grid.SetRow(cell, plan.Children.Count); }
                    plan.Children.Add(cell);
                }
                metricsBody.Children.Add(plan);
            }
            return true;
        }

        // A thin bar for a share of a whole: its own color when that is nearly the whole, over
        // a faint step of the same color.
        static Grid Meter(double share, bool warn, double from, Thickness margin)
        {
            Color ink = warn ? Ui.ContextFull : Colors.White;
            double shown = Math.Max(share, 0.02);
            var bar = new Grid { Height = 4, Margin = margin, VerticalAlignment = VerticalAlignment.Center };
            bar.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(shown, GridUnitType.Star) });
            bar.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(Math.Max(1 - share, 0), GridUnitType.Star) });
            var track = new Border { CornerRadius = new CornerRadius(2), Background = Ui.Alpha(ink, 0.18) };
            Grid.SetColumnSpan(track, 2);
            bar.Children.Add(track);
            var fill = new Border { CornerRadius = new CornerRadius(2), Background = Ui.Alpha(ink, warn ? 1 : 0.82) };
            bar.Children.Add(fill);
            // It glides from where the bar in this place stood before (another session's figure,
            // or nothing when the card has just come up) to where it stands now.
            if (!Ui.Motionless && from >= 0 && Math.Abs(from - share) > 0.005)
            {
                var stretch = new ScaleTransform(1, 1);
                fill.RenderTransformOrigin = new Point(0, 0.5);
                fill.RenderTransform = stretch;
                stretch.BeginAnimation(ScaleTransform.ScaleXProperty, new DoubleAnimation(from / shown, 1, TimeSpan.FromSeconds(GlideTakes)) { EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut } });
            }
            return bar;
        }

        // One figure of a session: its name, the figure, and a thin bar if it is a share of a
        // whole (the bar's own color when it is nearly the whole, over a faint step of the same).
        static UIElement Tile(string name, string figure, double share, bool warn, double from)
        {
            var tile = new StackPanel { Margin = new Thickness(0, 0, 12, 0) };
            tile.Children.Add(new TextBlock { Text = name, FontSize = 10.5, Foreground = Ui.Faint, TextTrimming = TextTrimming.CharacterEllipsis });
            var number = new TextBlock { FontSize = 16, FontWeight = FontWeights.SemiBold, Margin = new Thickness(0, 1, 0, 0) };
            int of = figure.IndexOf('/');
            if (figure.Length == 0) number.Inlines.Add(new Run("\u2013") { Foreground = Ui.Paint("#50FFFFFF"), FontWeight = FontWeights.Normal });  // not known
            else if (of > 0)  // "3/5": the part that is done stands out
            {
                number.Inlines.Add(new Run(figure.Substring(0, of)) { Foreground = Brushes.White });
                number.Inlines.Add(new Run(figure.Substring(of)) { Foreground = Ui.Faint, FontWeight = FontWeights.Normal });
            }
            else number.Inlines.Add(new Run(figure) { Foreground = warn ? Ui.Alpha(Ui.ContextFull, 1) : Brushes.White });
            tile.Children.Add(number);
            // share -2: bars are off, so no room is kept for one either
            if (share > -2) tile.Children.Add(share >= 0 ? (UIElement)Meter(share, warn, from, new Thickness(0, 4, 0, 0)) : new Border { Height = 4, Margin = new Thickness(0, 4, 0, 0) });
            return tile;
        }

        void BuildHistory()
        {
            historyLines.Children.Clear();
            string of = null;
            if (!historyAll)
            {
                foreach (Row row in order) if (row.Name == historyOf) of = row.Name;
                if (of == null) foreach (Row row in order) if (row.Focus) of = row.Name;
            }
            FillHistory(historyLines, of, of != null ? 4 : 6, true);
        }

        // The last lines said, newest first: of one session (`of`), or of all of them. Each
        // line has a small mark in front for how that turn ended, the sentence (the newest
        // brightest, older ones dimmer), and at its right end how long ago it was and what the
        // turn used; a white dot there marks a line that was never heard to its end.
        void FillHistory(Panel into, string of, int most, bool named)
        {
            int n = 0;
            Grid.SetIsSharedSizeScope(into, true);
            foreach (object o in history)
            {
                var h = (Dictionary<string, object>)o;
                if (of != null && Str(h, "name") != of) continue;
                if (n >= most) break;
                var line = new Grid { Margin = new Thickness(0, 2, 0, 2) };
                line.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
                line.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                line.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
                line.Children.Add(new EndMark(Str(h, "kind"), h.ContainsKey("missed") && h["missed"] != null && Convert.ToBoolean(h["missed"])));
                // The newest in full, up to five lines: the rows keep to one line each so the lights
                // never move, and the card of the session under the mouse is where to read it all
                // (the author, 2026-11-21: "showing the full words of the selected session").
                var words = new TextBlock { TextWrapping = TextWrapping.Wrap, FontSize = 12, MaxHeight = n == 0 && !named ? 84 : 34, TextTrimming = TextTrimming.CharacterEllipsis };
                if (named) words.Inlines.Add(new Run(Str(h, "name") + "  ") { FontWeight = FontWeights.SemiBold, Foreground = Ui.Named(Str(h, "color")) });
                words.Inlines.Add(new Run(Str(h, "text")) { Foreground = Ui.Alpha(Colors.White, n == 0 ? 0.94 : n == 1 ? 0.76 : n == 2 ? 0.64 : 0.55) });
                Grid.SetColumn(words, 1);
                line.Children.Add(words);
                // Two columns at the right, each as wide as its widest entry in this list, so the
                // times stand under one another and so do the tokens, with or without a figure.
                line.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto, SharedSizeGroup = "ago" });
                line.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto, SharedSizeGroup = "used" });
                string used = Str(h, "tokens");
                var ago = new TextBlock { Text = Str(h, "ago"), FontSize = 12, Foreground = Ui.Faint, Margin = new Thickness(Str(h, "ago").Length > 0 ? 8 : 0, 0, 0, 0), HorizontalAlignment = HorizontalAlignment.Right };
                Grid.SetColumn(ago, 3);
                line.Children.Add(ago);
                var spent = new TextBlock { Text = used, FontSize = 12, Foreground = Ui.Faint, Margin = new Thickness(used.Length > 0 ? 10 : 0, 0, 0, 0), HorizontalAlignment = HorizontalAlignment.Right };
                Grid.SetColumn(spent, 4);
                line.Children.Add(spent);
                into.Children.Add(line);
                n++;
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
            bool wantPeek = mode == "list" && (inside ? insideTicks >= historyTicks || peek : peek && outsideTicks < 9);
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
            bool sorting = onBar && CanReorder();
            bool wantCatch = (moving || (onBar && (dragKeys.Length == 0 || Held(dragKeys) || sorting))) && Ui.Now > passUntil;
            if (wantCatch != catching) { catching = wantCatch; rail.CatchMouse(catching); }
            bool panelWant = panelDrag && mode == "list" && panel.IsVisible && panel.Goal > 0 && Within(cursor, panel.Area(), 0) && Ui.Now > passUntil;
            if (panelWant != panelCatching) { panelCatching = panelWant; panel.CatchMouse(panelWant); }
            Edge();
            // The cursor says what a drag would do: arrows along the bar = put this light elsewhere,
            // the move cross = the bar is held only because its keys are. A bar that can always be
            // dragged keeps the plain arrow (the author did not like a move cursor at every pass).
            Cursor wanted = sorting && LightAt(cursor) != null ? (Island ? Cursors.SizeWE : Cursors.SizeNS)
                          : dragKeys.Length > 0 ? Cursors.SizeAll : Cursors.Arrow;
            if (rail.Cursor != wanted) rail.Cursor = wanted;
            if (under != hot)
            {
                hot = under;
                Run(true);
                if (hot != null && hot.Name != historyOf) { historyOf = hot.Name; if (IsOpen()) Render(); }  // its figures, and in list mode its history
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
            bool unsent = (talkState == "transcribing" || talkState == "ready" || talkState == "aside" || talkState == "sent" || talkState == "queued")
                && Ui.Now < talkUntil && Ui.Now < maskedUntil + 12;
            if (!holding && masked.Count > 0 && Ui.Now > maskedUntil && !unsent) masked.Clear();
            bool ahead = talkKey != 0 && (keepTalk == "always" || (keepTalk == "held" && talkMods != 0 && Mods(talkMods, false)));
            // Shared keys keep the hook in for as long as there are any: a press that came before
            // the hook would go to the other program alone.
            KeepKey((keepTalk != "off" && (holding || ahead || masked.Count > 0)) || shared.Count > 0);
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

        // A key held down for another program while you talk: Discord's Push to Mute (push_to_mute).
        // Sent marked as ours, so the hook here lets it through to the other programs' hooks.
        uint heldDown;
        public void HoldKey(uint key)
        {
            if (heldDown == key) return;
            if (heldDown != 0) Press((int)heldDown, true);
            heldDown = key;
            if (key != 0) Press((int)key, false);
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
            if (shared.Count > 0)  // a key another program reserved first: act on it, and pass it on to that program
            {
                bool up = message == WM_KEYUP || message == WM_SYSKEYUP;
                if (up) sharedDown.Remove(key);
                else if (down && !sharedDown.Contains(key))
                    foreach (KeyValuePair<string, uint[]> claim in shared)
                        if (claim.Value[0] == key && Mods(claim.Value[1], true))
                        {
                            string name = claim.Key;
                            sharedDown.Add(key);
                            rail.Dispatcher.BeginInvoke(new Action(delegate { Hotkey(name); }));
                            break;
                        }
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
            Edge();
            Run(true);  // the drag is followed frame by frame; with nothing else moving the frames had stopped
        }

        // The bar itself goes with the mouse: the panel and the bubble fold away while it travels.
        // Not while a light is being put elsewhere: with the details kept out, the panel folding
        // and coming back at every drop made the whole overlay look as if it had moved.
        void FoldForDrag()
        {
            hover = peek = false;
            Render();
            panel.Step(0, true);
            bubble.Step(0, true);
        }

        bool BarHeld { get { return dragging && !undecided && lifted == null; } }

        // A press on the kept-out details: the same as one on the bar, held where the bar is
        // from the cursor, except that it never puts a light elsewhere and the panel stays out.
        // Where it was pressed comes from the press, as for the bar (see BeginDrag).
        void PressPanel(Point at)
        {
            var source = PresentationSource.FromVisual(panel) as HwndSource;
            if (dragging || source == null) return;
            Point held = source.CompositionTarget.TransformToDevice.Transform(at);
            int[] box = panel.Area();
            grabbedAt = rail.Area();
            grabX = box[0] + (int)Math.Round(held.X) - grabbedAt[0];
            grabY = box[1] + (int)Math.Round(held.Y) - grabbedAt[1];
            dragging = panelHeld = undecided = true;
            Edge();
            // Without this a press on a still overlay was never followed: the drag was left
            // half begun, and every press after it was ignored (the author, 2026-11-19: "I
            // cannot move the layout right now").
            Run(true);
        }

        // Up while the voice is off and the bar is on screen; away while the bar travels, and
        // back in its place when it is dropped.
        void ShowMuteChip()
        {
            bool want = muted && mutedMark && rail.IsVisible && !BarHeld && !moving;
            if (want && !muteChip.IsVisible) { muteChip.Show(); PlaceSides(); }
            else if (!want && muteChip.IsVisible) muteChip.Hide();
        }

        void DragStep()
        {
            CursorPoint cursor;
            if (!GetCursorPos(out cursor)) return;
            int button = GetSystemMetrics(SM_SWAPBUTTON) != 0 ? VK_RBUTTON : VK_LBUTTON;
            if ((GetAsyncKeyState(button) & 0x8000) == 0) { EndDrag(); return; }
            if (undecided) Decide(cursor);
            if (undecided) return;
            if (lifted != null) { ReorderKeyed(); LiftStep(cursor); return; }
            Point to = HwndSource.FromHwnd(hwnd).CompositionTarget.TransformFromDevice.Transform(new Point(cursor.X - grabX, cursor.Y - grabY));
            rail.Left = to.X;
            rail.Top = to.Y;
            if (panelHeld) PlaceSides();
        }

        // Dropped. If it did not really move, the press was a plain click, and that goes to
        // whatever is underneath the bar.
        void EndDrag()
        {
            dragging = false;
            panelHeld = false;
            undecided = false;  // let go before it moved: the bar is where it was, so it was a click
            if (lifted != null) { EndLift(); return; }
            int[] now = rail.Area();
            if (Math.Abs(now[0] - grabbedAt[0]) + Math.Abs(now[1] - grabbedAt[1]) > 3)
            {
                ReportMoved();
                if (moving) { moveTimer.Stop(); moveTimer.Interval = TimeSpan.FromSeconds(2); moveTimer.Start(); }
            }
            else if (!moving) PassClick();
            insideTicks = outsideTicks = 0;
            Edge();
            Render();
            Place();
        }

        // A press that moved nothing was a plain click: it goes to whatever is underneath the bar.
        void PassClick()
        {
            passUntil = Ui.Now + 0.4;
            catching = panelCatching = false;
            rail.CatchMouse(false);
            panel.CatchMouse(false);
            mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, UIntPtr.Zero);
            mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, UIntPtr.Zero);
        }

        // --- putting sessions in another order --------------------------------------------------

        // With `reorder_keys` (Ctrl+Alt) held, a light dragged along the bar goes to another place
        // in it, and the others make room as it passes them; anywhere else a drag moves the bar.
        bool CanReorder()
        {
            return reorderKeys.Length > 0 && order.Count > 1 && !moving && Held(reorderKeys);
        }

        // How far along the bar a point on the screen is, in the bar's own units, from its first light.
        double AlongBar(CursorPoint at)
        {
            int[] bar = rail.Area();
            return Island ? (at.X - bar[0]) * rail.ActualWidth / Math.Max(1, bar[2]) - 4
                          : (at.Y - bar[1]) * rail.ActualHeight / Math.Max(1, bar[3]) - 4;
        }

        double Room(Row row) { return Island ? Row.High : row.Light.Height; }

        Row LightAt(CursorPoint at)
        {
            double along = AlongBar(at);
            foreach (Row row in order)
            {
                if (along >= 0 && along < Room(row)) return row;
                along -= Room(row);
            }
            return null;
        }

        // A press on the bar. What it does is decided once the mouse starts to move, not at the
        // press: Windows reported Ctrl and Alt still up at presses the author made with them, as
        // the press can come a moment before the keys, and those presses moved the whole overlay.
        void Press(Point at)
        {
            if (dragging) return;
            BeginDrag(at);
            if (!dragging) return;
            undecided = true;
            pressAlong = (Island ? at.X : at.Y) - 4;
        }

        bool ReorderKeyed()
        {
            if (reorderKeys.Length == 0 || order.Count < 2 || moving) return false;
            foreach (int key in reorderKeys) if (Pressed(key)) { reorderHeldAt = Ui.Now; return true; }
            return Ui.Now - reorderHeldAt < 0.4;  // let go a moment ago
        }

        // Until the mouse has moved a few pixels nothing moves. Any of the keys by then, or a
        // moment before: the light nearest the press is taken (also from the bar's rim or between
        // two lights); none: the bar goes with the mouse from where it was taken hold of.
        void Decide(CursorPoint cursor)
        {
            if (!panelHeld && ReorderKeyed())
            {
                undecided = false;
                double start = 0;
                Row row = order[order.Count - 1];
                foreach (Row r in order)
                {
                    if (pressAlong < start + Room(r)) { row = r; break; }
                    start += Room(r);
                }
                lifted = row;
                liftGrab = pressAlong;
                Panel.SetZIndex(row.Light, 1);
                Panel.SetZIndex(row.Text, 1);
                hot = null;  // nor does it keep the size a light has under the mouse
                return;
            }
            int[] bar = rail.Area();
            double dx = cursor.X - (bar[0] + grabX), dy = cursor.Y - (bar[1] + grabY);
            if (dx * dx + dy * dy < 36) return;  // 6 px
            undecided = false;
            if (!panelHeld) FoldForDrag();
            Edge();
            Send("note", "message", (panelHeld ? "overlay moved by its details" : "bar moved by the mouse") + ": ctrl " + (Down(VK_CONTROL) ? "down" : "up") + ", alt "
                 + (Down(VK_MENU) ? "down" : "up") + ", " + order.Count + " sessions");
        }

        // Where the light held would go if let go now: its middle, past how many others' middles.
        int LiftTarget(double moved)
        {
            int from = order.IndexOf(lifted);
            double start = 0;
            for (int i = 0; i < from; i++) start += Room(order[i]);
            double middle = start + Room(lifted) / 2 + moved, at = 0;
            int target = 0;
            foreach (Row row in order)
            {
                if (row == lifted) continue;
                if (at + Room(row) / 2 < middle) target++;
                at += Room(row);
            }
            return target;
        }

        void LiftStep(CursorPoint cursor)
        {
            int from = order.IndexOf(lifted);
            if (from < 0)  // that session ended meanwhile
            {
                foreach (Row r in order) { r.Shift.X = r.Shift.Y = r.TextShift.Y = 0; }
                lifted = null;
                dragging = false;
                Render();
                return;
            }
            double length = 0;
            foreach (Row row in order) length += Room(row);
            double start = 0;
            for (int i = 0; i < from; i++) start += Room(order[i]);
            double moved = Math.Max(-start, Math.Min(length - start - Room(lifted), AlongBar(cursor) - liftGrab));
            int target = LiftTarget(moved);
            double ease = still ? 1 : 0.35;
            for (int i = 0; i < order.Count; i++)
            {
                Row row = order[i];
                double goal = row == lifted ? moved
                            : i > from && i <= target ? -Room(lifted)
                            : i < from && i >= target ? Room(lifted) : 0;
                double now = Island ? row.Shift.X : row.Shift.Y;
                double next = row == lifted ? goal : now + (goal - now) * ease;
                if (Island) row.Shift.X = next; else row.Shift.Y = row.TextShift.Y = next;
            }
        }

        // Let go: the lights take their new places for good, and the hub is told the new order,
        // which it keeps. Hardly moved at all, it was a click, which goes to what is underneath.
        void EndLift()
        {
            Row row = lifted;
            double moved = Island ? row.Shift.X : row.Shift.Y;
            int from = order.IndexOf(row), target = from < 0 ? -1 : LiftTarget(moved);  // needs `lifted`
            lifted = null;
            foreach (Row r in order) { r.Shift.X = r.Shift.Y = r.TextShift.Y = 0; }
            Panel.SetZIndex(row.Light, 0);
            Panel.SetZIndex(row.Text, 0);
            if (from >= 0 && target != from)
            {
                order.RemoveAt(from);
                order.Insert(target, row);
                rowsPanel.Children.Clear();
                lights.Children.Clear();
                foreach (Row r in order) { rowsPanel.Children.Add(r.Text); lights.Children.Add(r.Light); }
                var names = new List<object>();
                foreach (Row r in order) names.Add(r.Name);
                Send("reorder", "names", names);
            }
            else if (Math.Abs(moved) < 3) PassClick();
            insideTicks = outsideTicks = 0;
            Edge();
            Render();
            Place();
        }

        // The bar's edge shows what the mouse can do: brighter when it can be grabbed, amber while held.
        void Edge()
        {
            bool keyed = catching && ((dragKeys.Length > 0 && Held(dragKeys)) || CanReorder());  // grabbable only because keys are held
            rail.Panel.BorderBrush = BarHeld || moving ? Ui.AmberEdge : keyed ? Ui.BrightEdge : Ui.GlassEdge;
        }

        // "sidetone overlay move": the same dragging, announced, for when the bar is hard to find.
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
            bannerHint.Text = dragKeys.Length == 0 ? "Any monitor. Later, just grab it with the mouse"
                                                   : "Any monitor. Later, hold " + dragKeysName + " to drag it";
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
        // (waiting for a go-ahead), aside (a side question being answered), sent, failed (text
        // says why), focus (a tap moved the focus).
        // It shows on the session it is about, and moves with the focus.
        void Talk(Dictionary<string, object> msg)
        {
            string state = Str(msg, "state");
            if (state == "listening" && talkState != "listening") mic.Clear();
            talkState = state;
            talkName = Str(msg, "name");
            talkText = Str(msg, "text");
            talkHint = Str(msg, "hint");
            talkQuiet = msg.ContainsKey("quiet") && Convert.ToBoolean(msg["quiet"]);
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
                case "transcribing": case "ready": case "aside": return "dots";
                case "sent": return "sent";
                case "queued": return Ui.WaitingMark == "clock" ? "wait" : "";  // else the number on the light says it
                case "failed": return "failed";
                case "stopped": return "stop";
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
                case "ready": case "aside": return "\u201c" + talkText + "\u201d" + (talkHint.Length > 0 ? "\n" + talkHint : "");
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
            return talkState == "ready" || talkState == "aside" || talkState == "sent" || talkState == "queued" ? Brushes.White : Ui.LiveInk;
        }

        // A permission prompt or question stays on screen until it is answered: the hotkeys act on it.
        static UIElement TickBox(bool on) { return new TickMark(on); }

        void ShowRequest(Dictionary<string, object> msg)
        {
            hasRequest = msg.ContainsKey("text");
            if (hasRequest)
            {
                requestTitle.Inlines.Clear();
                requestTitle.Inlines.Add(new Run("\u25B2  ") { Foreground = Ui.AmberEdge, FontFamily = Ui.Symbols });
                requestTitle.Inlines.Add(new Run(Str(msg, "name") + "  ") { FontWeight = FontWeights.SemiBold, Foreground = Ui.Named(Str(msg, "color")) });
                // Several questions in one dialog: which one this is, since the terminal goes on showing the first.
                if (Str(msg, "place").Length > 0) requestTitle.Inlines.Add(new Run("Question " + Str(msg, "place")) { Foreground = Ui.Dim });
                requestTitle.MaxHeight = Str(msg, "question").Length > 0 ? 74 : 54;  // the name's line and three more, or three in all
                if (Str(msg, "question").Length > 0)  // a question stands on a line of its own, under who asks it
                {
                    requestTitle.Inlines.Add(new LineBreak());
                    requestTitle.Inlines.Add(new Run(Str(msg, "question")) { Foreground = Brushes.White });
                }
                else requestTitle.Inlines.Add(new Run(Str(msg, "text")));
                object[] options = msg.ContainsKey("options") && msg["options"] != null ? (object[])msg["options"] : new object[0];
                // Several to tick: a box in front of each choice and no number (the keys go by
                // their order). One to pick: its number.
                object[] ticked = msg.ContainsKey("ticked") && msg["ticked"] != null ? (object[])msg["ticked"] : null;
                string detail = Str(msg, "detail");
                requestChoices.Children.Clear();
                if (options.Length > 0)  // a question: each choice in a row of its own, behind its number
                {
                    for (int i = 0; i < options.Length; i++)
                    {
                        UIElement mark;
                        double gap = 10;
                        if (ticked != null) mark = TickBox(i < ticked.Length && Convert.ToBoolean(ticked[i]));
                        else if (choiceCaps)  // the number as a key cap, like the keys below
                        {
                            mark = Cap((i + 1).ToString(CultureInfo.InvariantCulture), 0);
                            ((FrameworkElement)mark).Margin = new Thickness(0, 2, 0, 2);
                            gap = 7;
                        }
                        else mark = new TextBlock { Text = (i + 1).ToString(CultureInfo.InvariantCulture), FontWeight = FontWeights.SemiBold, Foreground = Ui.AmberEdge };
                        requestChoices.Children.Add(Choice(mark, Convert.ToString(options[i], CultureInfo.InvariantCulture), gap, ticked == null && choiceCaps ? 2 : 0));
                    }
                }
                else  // a permission prompt: the exact command or path
                {
                    requestDetail.MaxHeight = 70;  // about four lines; the terminal has the full command
                    requestDetail.Text = detail;
                }
                requestDetail.Visibility = options.Length == 0 && detail.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
                requestChoices.Visibility = options.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
                requestKeys.Text = Str(msg, "keys");
                object[] hints = msg.ContainsKey("hints") && msg["hints"] is object[] ? (object[])msg["hints"] : new object[0];
                requestCaps.Children.Clear();
                if (hints.Length > 0) Caps(hints);
                requestKeys.Visibility = requestCaps.Children.Count > 0 ? Visibility.Collapsed : Visibility.Visible;
                requestCaps.Visibility = requestCaps.Children.Count > 0 ? Visibility.Visible : Visibility.Collapsed;
                // How many more wait: on a line of its own under the caps, always in the same
                // place (at the end of the caps it fitted for two keys and broke off for five).
                // Without caps the line of text about the keys says it.
                int more = (int)Num(msg, "more", 0);
                requestMore.Text = more + " more waiting";
                requestMore.Visibility = more > 0 && requestCaps.Children.Count > 0 ? Visibility.Visible : Visibility.Collapsed;
            }
            Render();
        }

        // The keys of a request as caps, all alike and all the same distance apart. Keys that
        // begin alike ("Ctrl+Alt+Y", "Ctrl+Alt+N") show that beginning once, then a plus, then
        // one cap for each with what it does: [Ctrl] [Alt] + [Y] allow  [N] deny. A run of
        // number keys is written out, [1] [2] [3], one cap for each choice in its order (as a
        // range, "1-3", it was not clear to someone who does not know the keys).
        void Caps(object[] hints)
        {
            var parts = new List<string[]>();  // the keys before the last, the last key, what it does, the last key of a run
            foreach (object o in hints)
            {
                var hint = o as object[];
                if (hint == null || hint.Length < 2) continue;
                string combo = Convert.ToString(hint[0], CultureInfo.InvariantCulture), does = Convert.ToString(hint[1], CultureInfo.InvariantCulture);
                string to = hint.Length > 2 ? Convert.ToString(hint[2], CultureInfo.InvariantCulture) : "";
                int cut = combo.LastIndexOf('+');
                string last = cut >= 0 ? combo.Substring(cut + 1) : combo;
                if (last.Length == 0) continue;
                parts.Add(new[] { cut >= 0 ? combo.Substring(0, cut) : "", last, does, to });
            }
            if (parts.Count == 0) return;
            bool alike = parts[0][0].Length > 0;
            foreach (string[] part in parts) alike &= part[0] == parts[0][0];
            if (alike)
            {
                foreach (string key in parts[0][0].Split('+')) requestCaps.Children.Add(Cap(key, CapGap));
                requestCaps.Children.Add(new TextBlock { Text = "+", Foreground = Ui.AmberEdge, Margin = new Thickness(1, 0, 1 + CapGap, 4), VerticalAlignment = VerticalAlignment.Center });
            }
            foreach (string[] part in parts)
            {
                if (!alike && part[0].Length > 0) foreach (string key in part[0].Split('+')) requestCaps.Children.Add(Cap(key, CapGap));
                int first, last;
                if (part[3].Length > 0 && int.TryParse(part[1], out first) && int.TryParse(part[3], out last) && last > first && last - first < 9)
                    for (int n = first; n <= last; n++) requestCaps.Children.Add(Cap(n.ToString(CultureInfo.InvariantCulture), CapGap));
                else requestCaps.Children.Add(Cap(part[3].Length > 0 && part[3] != part[1] ? part[1] + "\u2013" + part[3] : part[1], CapGap));
                requestCaps.Children.Add(new TextBlock { Text = part[2], Foreground = Ui.AmberEdge, Margin = new Thickness(2, 0, 14, 4), VerticalAlignment = VerticalAlignment.Center });
            }
        }

        // One choice of a question: its mark (number, key cap or tick box) and then its words,
        // which wrap under their own first word and not under the mark. `down`: how far the
        // words sit below the top of the row, for a mark that is taller than a line of text.
        static Grid Choice(UIElement mark, string words, double gap, double down)
        {
            var row = new Grid();
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            var holder = new Border { Child = mark, VerticalAlignment = VerticalAlignment.Top, HorizontalAlignment = HorizontalAlignment.Left, Margin = new Thickness(0, 0, gap, 0) };
            var text = new TextBlock { Text = words, Foreground = Brushes.White, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, down, 0, 0), VerticalAlignment = VerticalAlignment.Top };
            Grid.SetColumn(text, 1);
            row.Children.Add(holder);
            row.Children.Add(text);
            return row;
        }

        const double CapGap = 4;  // between one cap and the next

        // One key, drawn as a key: every cap has the same look. `gap`: the room to its right
        // (and under it, where a line of caps may wrap); 0 for one that stands in a line of text.
        static Border Cap(string key, double gap)
        {
            return new Border {
                CornerRadius = new CornerRadius(4), BorderThickness = new Thickness(1), Padding = new Thickness(5, 0, 5, 1),
                Margin = new Thickness(0, 0, gap, gap), VerticalAlignment = VerticalAlignment.Center, MinWidth = 21,
                BorderBrush = Ui.Alpha(Ui.Amber, 0.80), Background = Ui.Alpha(Ui.Amber, 0.16),
                // Its own line height: a cap in a line of text would take that text's, and grow tall.
                Child = new TextBlock { Text = key, FontSize = 11.5, FontWeight = FontWeights.SemiBold, Foreground = Brushes.White, HorizontalAlignment = HorizontalAlignment.Center, LineHeight = double.NaN },
            };
        }

        // The voice off or on, as one row: the speaker (struck out, or sounding in the blue of
        // "working"), the words, and the key beside them. The mute key's banner and the line in the
        // details while muted are this same row, so nothing moves when one gives way to the other
        // (the author, 2026-11-19: "one layout does enough ... the side-by-side is good"), and the
        // speaker is the same drawing at the same size and gap both ways (they saw the emoji
        // speaker of "Voice on" sit out of line with its words).
        void VoiceRow(TextBlock row, bool muted, string text, string hint)
        {
            row.Inlines.Clear();
            var speaker = new MutedSpeaker(15) { Struck = muted, Margin = new Thickness(0, 0, 7, -2) };
            if (!muted) speaker.Ink = Ui.Alpha(Ui.Tint("working"), 1);
            row.Inlines.Add(new InlineUIContainer(speaker) { BaselineAlignment = BaselineAlignment.Center });
            row.Inlines.Add(new Run(text) { Foreground = Ui.Dim });
            if (hint.Length > 0) row.Inlines.Add(new Run("   " + hint) { Foreground = Ui.Faint, FontSize = 11.5 });
        }

        // Push-to-talk feedback: who is being recorded for, the transcript about to be sent, and so on.
        void ShowBanner(Dictionary<string, object> msg)
        {
            bannerTimer.Stop();
            hasBanner = msg.ContainsKey("text") && msg["text"] != null;
            if (hasBanner)
            {
                bannerTitle.Inlines.Clear();
                // The microphone (moving the bar), or a speaker struck out or sounding (the mute key).
                string icon = Str(msg, "icon", "");
                if (icon == "muted" || icon == "voice")
                {
                    VoiceRow(bannerTitle, icon == "muted", Str(msg, "text"), Str(msg, "hint"));
                    bannerHint.Text = "";
                }
                else if (icon == "clear")  // the clear key asks, as the mute key's row says what it did; a bin (an eraser was first: "I don't like it much")
                {
                    bannerTitle.Inlines.Add(new Run("\uE74D") { FontFamily = new FontFamily("Segoe Fluent Icons, Segoe MDL2 Assets"), FontSize = 14,
                        Foreground = Ui.Alpha(Ui.Tint("working"), 1), BaselineAlignment = BaselineAlignment.Center });
                    bannerTitle.Inlines.Add(new Run("  " + Str(msg, "text")) { Foreground = Ui.Dim });
                    string confirm = Str(msg, "hint");
                    if (confirm.Length > 0) bannerTitle.Inlines.Add(new Run("   " + confirm) { Foreground = Ui.Faint, FontSize = 11.5 });
                    bannerHint.Text = "";
                }
                else
                {
                    bannerTitle.Inlines.Add(new Run("\uD83C\uDFA4  ") { Foreground = Ui.Alpha(Ui.Tint("working"), 1), FontFamily = Ui.Symbols });
                    bannerTitle.Inlines.Add(new Run(Str(msg, "text")) { FontWeight = FontWeights.SemiBold });
                    bannerHint.Text = Str(msg, "hint");
                }
                bannerHint.Visibility = bannerHint.Text.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
                double seconds = Num(msg, "seconds", 0);
                if (seconds > 0) { bannerTimer.Interval = TimeSpan.FromSeconds(seconds); bannerTimer.Start(); }
            }
            Render();
        }

        void SetMode(string wanted)
        {
            // "focus" (Selected Only) is like "dots" with the session in focus kept in the bubble;
            // the details key goes from either to "list" and back to the one it came from.
            if (mode != "list") restMode = mode;
            mode = wanted == "toggle" ? (mode == "list" ? restMode : "list") : (wanted == "list" || wanted == "focus" ? wanted : "dots");
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
            // The mute mark: past the end of the bar that is away from the screen's edge (under a
            // bar at the top, over one at the bottom), or at the right end of the island.
            if (Island) { muteChip.Left = rail.Left + width + ChipGap; muteChip.Top = rail.Top + (height - ChipSize) / 2; }
            else
            {
                muteChip.Left = rail.Left + (width - ChipSize) / 2;
                muteChip.Top = bottom ? rail.Top - ChipGap - ChipSize : rail.Top + height + ChipGap;
            }
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
        // programs the rest of the time; so are the keys that move the focus and the one that goes
        // to a session's terminal (jump). The others (toggle, talk, repeat, ...) are always claimed.
        void RegisterHotkeys()
        {
            foreach (int id in hotkeys.Keys) UnregisterHotKey(hwnd, id);
            hotkeys.Clear();
            hotkeyKeys.Clear();
            claims.Clear();
            shared.Clear();
            talkKey = talkMods = 0;
            if (typingKey) return;  // the keys pressed now are a new hotkey being chosen, not ours to act on
            int next = 1;
            foreach (KeyValuePair<string, string> entry in wantedKeys)
            {
                bool answers = entry.Key == "allow" || entry.Key == "deny" || entry.Key == "cancel" || entry.Key == "jump" || entry.Key == "clear" || entry.Key.StartsWith("option") || entry.Key.StartsWith("focus_");
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
                else if (shareTaken && entry.Key != "talk")
                {
                    shared[entry.Key] = new uint[] { vk, modifiers & ~MOD_NOREPEAT };
                    if (complained.Add(combo)) Error("hotkey " + combo + " is already taken by another program; listening for it as well, so both act on it");
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
                if (muteChip.IsVisible) pieces.Add(muteChip.Area());
                if (settings != null && settings.IsOpen) pieces.Add(settings.Window.Area());
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
