// What a headset button press becomes on this Windows, tried by hand with a voice saying each step.
// Not part of Sidetone: see "AirPods paired with the PC" in TODO.md. Run: tests/headset/run.sh [--mic=NAME]. C# 5.
using System; using System.Collections.Generic; using System.Diagnostics; using System.Drawing; using System.IO;
using System.Linq; using System.Media; using System.Runtime.InteropServices; using System.Runtime.InteropServices.WindowsRuntime;
using System.Speech.Synthesis; using System.Text; using System.Threading; using System.Windows.Forms;
using Windows.ApplicationModel.Calls; using Windows.Devices.Enumeration; using Windows.Media; using Windows.Media.Control;

[ComImport, Guid("ddb0472d-c911-4a1f-86d9-dc3d71a95f5a"), InterfaceType(ComInterfaceType.InterfaceIsIInspectable)]
interface ISmtcInterop { SystemMediaTransportControls GetForWindow(IntPtr window, [In] ref Guid riid); }

class Mic {
    [StructLayout(LayoutKind.Sequential)] public struct Fmt { public short tag, ch; public int rate, bps; public short align, bits, extra; }
    [StructLayout(LayoutKind.Sequential)] struct Hdr { public IntPtr data; public int len, rec; public IntPtr user; public int flags, loops; public IntPtr next, res; }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] struct Caps { public short mid, pid; public int ver; [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string name; public int formats; public short ch, res; }
    [DllImport("winmm.dll")] static extern int waveInGetNumDevs();
    [DllImport("winmm.dll", CharSet = CharSet.Unicode)] static extern int waveInGetDevCapsW(IntPtr id, ref Caps c, int size);
    [DllImport("winmm.dll")] static extern int waveInOpen(out IntPtr h, int id, ref Fmt f, IntPtr cb, IntPtr inst, int flags);
    [DllImport("winmm.dll")] static extern int waveInPrepareHeader(IntPtr h, IntPtr hdr, int size);
    [DllImport("winmm.dll")] static extern int waveInAddBuffer(IntPtr h, IntPtr hdr, int size);
    [DllImport("winmm.dll")] static extern int waveInStart(IntPtr h);
    [DllImport("winmm.dll")] static extern int waveInReset(IntPtr h);
    [DllImport("winmm.dll")] static extern int waveInUnprepareHeader(IntPtr h, IntPtr hdr, int size);
    [DllImport("winmm.dll")] static extern int waveInClose(IntPtr h);
    public static List<string> Names() {
        var l = new List<string>();
        for (int i = 0; i < waveInGetNumDevs(); i++) { var c = new Caps(); waveInGetDevCapsW((IntPtr)i, ref c, Marshal.SizeOf(typeof(Caps))); l.Add(c.name); }
        return l;
    }
    // Records until stop is set; firstBuffer is called once, when audio arrives.
    public static void Record(string match, string wav, Func<bool> stop, Action firstBuffer) {
        int id = Names().FindIndex(x => x.IndexOf(match, StringComparison.OrdinalIgnoreCase) >= 0);
        if (id < 0) { App.Log("MIC", "no microphone named " + match); return; }
        var f = new Fmt { tag = 1, ch = 1, rate = 16000, bps = 32000, align = 2, bits = 16 };
        var sw = Stopwatch.StartNew(); IntPtr h;
        int r = waveInOpen(out h, id, ref f, IntPtr.Zero, IntPtr.Zero, 0);
        App.Log("MIC", "open " + Names()[id] + " result " + r + " after " + sw.ElapsedMilliseconds + " ms");
        if (r != 0) return;
        int hs = Marshal.SizeOf(typeof(Hdr)), n = 8, len = 1600; var hdrs = new IntPtr[n]; var bufs = new IntPtr[n];
        var pcm = new MemoryStream(); bool first = true; bool sound = false; int peak = 0; long lastSec = 0;
        for (int i = 0; i < n; i++) {
            bufs[i] = Marshal.AllocHGlobal(len); hdrs[i] = Marshal.AllocHGlobal(hs);
            Marshal.StructureToPtr(new Hdr { data = bufs[i], len = len }, hdrs[i], false);
            waveInPrepareHeader(h, hdrs[i], hs); waveInAddBuffer(h, hdrs[i], hs);
        }
        waveInStart(h); int k = 0;
        while (!stop()) {
            var hd = (Hdr)Marshal.PtrToStructure(hdrs[k], typeof(Hdr));
            if ((hd.flags & 1) == 0) { Thread.Sleep(5); continue; }
            var b = new byte[hd.rec]; Marshal.Copy(bufs[k], b, 0, hd.rec); pcm.Write(b, 0, b.Length);
            for (int j = 0; j + 1 < b.Length; j += 2) peak = Math.Max(peak, Math.Abs((int)BitConverter.ToInt16(b, j)));
            if (first) { first = false; App.Log("MIC", "first buffer after " + sw.ElapsedMilliseconds + " ms, peak " + peak); firstBuffer(); }
            if (!sound && peak > 200) { sound = true; App.Log("MIC", "first sound after " + sw.ElapsedMilliseconds + " ms"); }
            if (sw.ElapsedMilliseconds - lastSec > 1000) { lastSec = sw.ElapsedMilliseconds; App.Log("MIC", "level " + peak); peak = 0; }
            hd.flags &= ~1; Marshal.StructureToPtr(hd, hdrs[k], false); waveInAddBuffer(h, hdrs[k], hs); k = (k + 1) % n;
        }
        sw.Restart(); waveInReset(h);
        for (int i = 0; i < n; i++) { waveInUnprepareHeader(h, hdrs[i], hs); Marshal.FreeHGlobal(hdrs[i]); Marshal.FreeHGlobal(bufs[i]); }
        waveInClose(h); App.Log("MIC", "closed, took " + sw.ElapsedMilliseconds + " ms");
        File.WriteAllBytes(wav, App.Wav(pcm.ToArray(), 16000));
    }
}

class App : Form {
    static App me; static StreamWriter log; static readonly Stopwatch clock = Stopwatch.StartNew(); static readonly object gate = new object();
    static string dir, match = "Bose"; static int heard; static bool check; volatile bool quit;
    readonly TextBox box = new TextBox(); readonly Button go = new Button();
    SystemMediaTransportControls smtc; VoipPhoneCall call; VoipCallCoordinator coord; SpeechSynthesizer voice;
    delegate IntPtr Hook(int code, IntPtr w, IntPtr l); Hook proc; IntPtr hook;
    [DllImport("user32.dll")] static extern IntPtr SetWindowsHookEx(int kind, Hook p, IntPtr m, uint t);
    [DllImport("user32.dll")] static extern bool UnhookWindowsHookEx(IntPtr h);
    [DllImport("user32.dll")] static extern IntPtr CallNextHookEx(IntPtr h, int c, IntPtr w, IntPtr l);
    [DllImport("kernel32.dll")] static extern IntPtr GetModuleHandle(string n);

    public static void Log(string tag, string text) {
        string line = string.Format("{0,8:0.000} {1,-6} {2}", clock.Elapsed.TotalSeconds, tag, text);
        lock (gate) { log.WriteLine(line); log.Flush(); Console.WriteLine(line); }
        if (me != null && me.IsHandleCreated) try { me.BeginInvoke((Action)(() => me.box.AppendText(line + "\r\n"))); } catch { }
    }
    static volatile bool armed; static string last = "";
    static void Event(string tag, string text) { Log(tag, text + (armed ? "" : "   (not counted)")); if (!armed) return; heard++; last = text; if (!check) Beep(1320, 90); }
    public static byte[] Wav(byte[] pcm, int rate) {
        var m = new MemoryStream(); var w = new BinaryWriter(m);
        w.Write(Encoding.ASCII.GetBytes("RIFF")); w.Write(36 + pcm.Length); w.Write(Encoding.ASCII.GetBytes("WAVEfmt ")); w.Write(16);
        w.Write((short)1); w.Write((short)1); w.Write(rate); w.Write(rate * 2); w.Write((short)2); w.Write((short)16);
        w.Write(Encoding.ASCII.GetBytes("data")); w.Write(pcm.Length); w.Write(pcm); w.Flush(); return m.ToArray();
    }
    static void Beep(int hz, int ms) {
        ThreadPool.QueueUserWorkItem(delegate {
            int n = 22050 * ms / 1000; var b = new byte[n * 2];
            for (int i = 0; i < n; i++) { double fade = Math.Min(1, Math.Min(i, n - i) / 200.0); var v = (short)(7000 * fade * Math.Sin(2 * Math.PI * hz * i / 22050)); b[2 * i] = (byte)v; b[2 * i + 1] = (byte)(v >> 8); }
            try { using (var p = new SoundPlayer(new MemoryStream(Wav(b, 22050)))) p.PlaySync(); } catch (Exception e) { Log("BEEP", e.Message); }
        });
    }
    App() {
        me = this; Text = "Sidetone headset test"; TopMost = true; Size = new Size(760, 420); StartPosition = FormStartPosition.CenterScreen;
        go.Text = "Start (put the headphones on, then you can walk to the kitchen)"; go.Dock = DockStyle.Top; go.Height = 64; go.Font = new Font("Segoe UI", 13);
        box.Multiline = true; box.Dock = DockStyle.Fill; box.ReadOnly = true; box.ScrollBars = ScrollBars.Vertical; box.Font = new Font("Consolas", 10);
        Controls.Add(box); Controls.Add(go);
        go.Click += delegate { go.Enabled = false; var t = new Thread(Run); t.IsBackground = true; t.Start(); };
        Shown += delegate {
            proc = OnKey; hook = SetWindowsHookEx(13, proc, GetModuleHandle(null), 0); Log("HOOK", "installed " + (hook != IntPtr.Zero));
            if (check) { var t = new Thread(Check); t.IsBackground = true; t.Start(); }
        };
        FormClosing += delegate { quit = true; Cleanup(); ResumeMusic(); if (hook != IntPtr.Zero) UnhookWindowsHookEx(hook); };
    }
    IntPtr OnKey(int code, IntPtr w, IntPtr l) {
        if (code >= 0) {
            int vk = Marshal.ReadInt32(l), flags = Marshal.ReadInt32(l, 8);
            if (vk >= 0xAD && vk <= 0xB7) { string t = "key 0x" + vk.ToString("X") + ((flags & 0x80) != 0 ? " up" : " down") + ((flags & 0x10) != 0 ? " injected" : ""); ThreadPool.QueueUserWorkItem(delegate { Event("HOOK", t); }); }
        }
        return CallNextHookEx(hook, code, w, l);
    }
    static T Get<T>(Windows.Foundation.IAsyncOperation<T> op) { for (int i = 0; i < 3000 && op.Status == Windows.Foundation.AsyncStatus.Started; i++) Thread.Sleep(10); return op.GetResults(); }
    void Ui(Action a) { Invoke(a); }
    void Claim() {
        Ui(delegate {
            try {
                if (smtc == null) {
                    var f = (ISmtcInterop)WindowsRuntimeMarshal.GetActivationFactory(typeof(SystemMediaTransportControls));
                    var iid = new Guid("99FA3FF4-1742-42A6-902E-087D41F965EC"); smtc = f.GetForWindow(Handle, ref iid);
                    smtc.ButtonPressed += (s, e) => Event("SMTC", e.Button.ToString());
                }
                smtc.IsEnabled = true; smtc.IsPlayEnabled = smtc.IsPauseEnabled = smtc.IsStopEnabled = smtc.IsNextEnabled = smtc.IsPreviousEnabled = true;
                smtc.DisplayUpdater.Type = MediaPlaybackType.Music; smtc.DisplayUpdater.MusicProperties.Title = "Sidetone headset test"; smtc.DisplayUpdater.Update();
                smtc.PlaybackStatus = MediaPlaybackStatus.Paused; Log("SMTC", "claimed, paused");
            } catch (Exception e) { Log("SMTC", "failed: " + e); }
        });
    }
    void Release() { if (smtc != null) try { smtc.PlaybackStatus = MediaPlaybackStatus.Closed; smtc.IsEnabled = false; Log("SMTC", "released"); } catch { } }
    void Sessions() {
        try {
            var m = Get(GlobalSystemMediaTransportControlsSessionManager.RequestAsync()); var cur = m.GetCurrentSession();
            Log("MEDIA", "current: " + (cur == null ? "none" : cur.SourceAppUserModelId));
            foreach (var s in m.GetSessions()) Log("MEDIA", "  " + s.SourceAppUserModelId + " " + s.GetPlaybackInfo().PlaybackStatus);
        } catch (Exception e) { Log("MEDIA", "failed: " + e.Message); }
    }
    List<string> ids; readonly List<GlobalSystemMediaTransportControlsSession> paused = new List<GlobalSystemMediaTransportControlsSession>();
    void PauseMusic() {
        try { foreach (var s in Get(GlobalSystemMediaTransportControlsSessionManager.RequestAsync()).GetSessions())
            if (!s.SourceAppUserModelId.StartsWith("HeadsetTest") && s.GetPlaybackInfo().PlaybackStatus == GlobalSystemMediaTransportControlsSessionPlaybackStatus.Playing) {
                Log("MEDIA", "pausing " + s.SourceAppUserModelId + ": " + Get(s.TryPauseAsync())); if (!paused.Any(x => x.SourceAppUserModelId == s.SourceAppUserModelId)) paused.Add(s); }
        } catch (Exception e) { Log("MEDIA", "pause failed: " + e.Message); }
        Wait(1);
    }
    void ResumeMusic() { foreach (var s in paused) try { Log("MEDIA", "resuming " + Get(s.TryPlayAsync())); } catch (Exception e) { Log("MEDIA", e.Message); } paused.Clear(); }
    void Playing() { Ui(delegate { if (smtc != null) { smtc.PlaybackStatus = MediaPlaybackStatus.Closed; smtc.IsEnabled = false; Thread.Sleep(100); smtc.IsEnabled = true; smtc.IsPlayEnabled = smtc.IsPauseEnabled = smtc.IsStopEnabled = smtc.IsNextEnabled = smtc.IsPreviousEnabled = true; smtc.PlaybackStatus = MediaPlaybackStatus.Playing; smtc.DisplayUpdater.Update(); Log("SMTC", "playing"); } }); Wait(1); Sessions(); }
    List<string> Devices() {
        coord = coord ?? VoipCallCoordinator.GetDefault();
        Log("VOIP", "bluetooth call control supported: " + VoipCallCoordinator.IsCallControlDeviceKindSupportedForAssociation(VoipCallControlDeviceKind.Bluetooth));
        var d = Get(DeviceInformation.FindAllAsync(VoipCallCoordinator.GetDeviceSelectorForCallControl()));
        foreach (var x in d) Log("VOIP", "device " + x.Name);
        return d.Where(x => x.Name.IndexOf(match, StringComparison.OrdinalIgnoreCase) >= 0).Select(x => x.Id).ToList();
    }
    void StartCall() {
        try {
            coord.MuteStateChanged += (s, e) => Event("VOIP", "mute changed, muted " + e.Muted);
            call = coord.RequestNewOutgoingCall("sidetone-test", "Sidetone", "Sidetone headset test", VoipPhoneCallMedia.Audio);
            call.EndRequested += (s, e) => { Event("VOIP", "end requested"); EndCall(); };
            call.HoldRequested += (s, e) => Event("VOIP", "hold requested"); call.ResumeRequested += (s, e) => Event("VOIP", "resume requested");
            call.AnswerRequested += (s, e) => Event("VOIP", "answer requested"); call.RejectRequested += (s, e) => Event("VOIP", "reject requested");
            if (ids.Count > 0) call.NotifyCallActive(ids); else call.NotifyCallActive();
            Log("VOIP", "call active, devices " + ids.Count);
        } catch (Exception e) { Log("VOIP", "failed: " + e); }
    }
    void EndCall() { var c = call; call = null; if (c != null) try { c.NotifyCallEnded(); Log("VOIP", "call ended"); } catch (Exception e) { Log("VOIP", e.Message); } }
    void Cleanup() { EndCall(); Release(); }
    void Say(string s) { if (quit) return; Log("SAY", s); try { voice.Speak(s); } catch (Exception e) { Log("SAY", e.Message); } }
    void Wait(double s) { var w = Stopwatch.StartNew(); while (!quit && w.Elapsed.TotalSeconds < s) Thread.Sleep(50); }
    void Ask(string say, double seconds) {
        Say(say); Wait(0.3); Beep(660, 400); Wait(0.5); int before = heard; armed = true; Log("ASK", say + " | listening " + seconds + " s");
        Wait(seconds); armed = false; Log("ASK", "counted events: " + (heard - before));
        Say(heard > before ? "I heard: " + last + "." : "Nothing arrived.");
    }
    void Presses(bool withCall) {
        bool stop = false; var ready = new ManualResetEvent(false);
        var t = new Thread(() => Mic.Record(match, Path.Combine(dir, withCall ? "mic-call.wav" : "mic.wav"), () => stop || quit, delegate { ready.Set(); })); t.IsBackground = true; t.Start();
        if (!ready.WaitOne(8000)) { Say("The microphone did not open."); stop = true; t.Join(3000); return; }
        Wait(2);
        foreach (var p in new[] { "Press once.", "Press twice quickly.", "Press and hold for two seconds." }) {
            if (quit) break;
            if (withCall && call == null) { StartCall(); Wait(3); }  // the call's own start sends mute events
            Ask("After the tone: " + p, 8);
        }
        EndCall(); stop = true; t.Join(5000); Wait(7);
    }
    void Run() {
        try {
            voice = new SpeechSynthesizer(); voice.SetOutputToDefaultAudioDevice(); Sessions(); PauseMusic();
            try { ids = Devices(); } catch (Exception e) { ids = new List<string>(); Log("VOIP", e.Message); }
            Say("Second headset test. Always wait for the tone, then press. I start in ten seconds."); Wait(10);
            Claim(); Wait(1); Sessions();
            Ask("Warm up, microphone closed. After the tone: press once.", 8);
            Say("Now the microphone opens."); Presses(false); Sessions();
            Say("Now the microphone opens, with a pretend phone call."); Presses(true); Sessions();
            if (paused.Count > 0) {
                Say("Now with your music playing. I start it."); ResumeMusic(); Wait(3); Sessions();
                Ask("After the tone: take the headphones off, wait three seconds, put them back on.", 15); Sessions();
                Ask("After the tone: press once.", 8); Sessions();
            }
            Say("Finished. Claude will read the result.");
        } catch (Exception e) { Log("ERROR", e.ToString()); }
        Cleanup(); ResumeMusic(); if (!quit) Ui(Close);
    }
    void Check() {
        try { Sessions(); foreach (var n in Mic.Names()) Log("MIC", "have " + n); Claim(); Wait(1); Sessions(); Devices();
            voice = new SpeechSynthesizer(); foreach (var v in voice.GetInstalledVoices()) Log("SAY", "voice " + v.VoiceInfo.Name);
            var t = Stopwatch.StartNew(); Mic.Record("Nuroum", Path.Combine(dir, "check.wav"), () => t.Elapsed.TotalSeconds > 2, delegate { });
        } catch (Exception e) { Log("ERROR", e.ToString()); }
        Cleanup(); Ui(Close);
    }
    [STAThread] static void Main(string[] a) {
        dir = AppDomain.CurrentDomain.BaseDirectory; check = a.Contains("--check");
        foreach (var x in a) if (x.StartsWith("--mic=")) match = x.Substring(6);
        log = new StreamWriter(Path.Combine(dir, check ? "check.log" : "headset-" + DateTime.Now.ToString("HHmmss") + ".log"));
        Application.EnableVisualStyles(); var f = new App(); if (check) f.WindowState = FormWindowState.Minimized; Application.Run(f); log.Close();
    }
}
