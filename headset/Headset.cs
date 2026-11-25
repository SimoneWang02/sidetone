// Talking through a headset: its button reaches Windows as a media button, so this holds a media
// session of its own while the hub wants the button, opens the microphone of the headphones you
// are listening on, and reports a call while it is open, which is how a headset's button comes back
// from then on (as "end the call"). It decides nothing: see hub/headset.py and docs/dev/features.md.
// Compiled by the hub with Windows' own csc.exe (C# 5, ASCII); CALLS is defined where Windows has
// call control devices (11 24H2).
// In, a word a line: hold, release, open, close, drop. Out, JSON a line: ready, press, opened, audio,
// end, closed, error, note.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Media;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.WindowsRuntime;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using Windows.ApplicationModel.Calls;
using Windows.Devices.Enumeration;
using Windows.Media;
using Windows.Media.Control;
using Windows.Media.Devices;

[ComImport, Guid("ddb0472d-c911-4a1f-86d9-dc3d71a95f5a"), InterfaceType(ComInterfaceType.InterfaceIsIInspectable)]
interface ISmtcInterop { SystemMediaTransportControls GetForWindow(IntPtr window, [In] ref Guid riid); }

static class Out
{
    static readonly object gate = new object();
    static readonly Stream stream = Console.OpenStandardOutput();

    static string Quote(string text)
    {
        var b = new StringBuilder("\"");
        foreach (char c in text ?? "")
        {
            if (c == '"' || c == '\\') b.Append('\\').Append(c);
            else if (c < 32 || c > 126) b.Append("\\u").Append(((int)c).ToString("x4"));
            else b.Append(c);
        }
        return b.Append('"').ToString();
    }

    public static void Send(string type, string key = null, string value = null, string more = "")
    {
        byte[] line = Encoding.ASCII.GetBytes("{\"type\":" + Quote(type) + (key == null ? "" : "," + Quote(key) + ":" + Quote(value)) + more + "}\n");
        lock (gate) { try { stream.Write(line, 0, line.Length); stream.Flush(); } catch (IOException) { Environment.Exit(0); } }
    }
}

// The microphone of the headphones in use, 16 kHz mono, as it comes.
class Microphone
{
    [StructLayout(LayoutKind.Sequential)] struct Format { public short tag, channels; public int rate, bytes; public short align, bits, extra; }
    [StructLayout(LayoutKind.Sequential)] struct Header { public IntPtr data; public int length, recorded; public IntPtr user; public int flags, loops; public IntPtr next, reserved; }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct Caps { public short maker, product; public int version; [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string name; public int formats; public short channels, reserved; }
    [DllImport("winmm.dll")] static extern int waveInGetNumDevs();
    [DllImport("winmm.dll", CharSet = CharSet.Unicode)] static extern int waveInGetDevCapsW(IntPtr id, ref Caps caps, int size);
    [DllImport("winmm.dll")] static extern int waveInOpen(out IntPtr handle, int id, ref Format format, IntPtr callback, IntPtr instance, int flags);
    [DllImport("winmm.dll")] static extern int waveInPrepareHeader(IntPtr handle, IntPtr header, int size);
    [DllImport("winmm.dll")] static extern int waveInUnprepareHeader(IntPtr handle, IntPtr header, int size);
    [DllImport("winmm.dll")] static extern int waveInAddBuffer(IntPtr handle, IntPtr header, int size);
    [DllImport("winmm.dll")] static extern int waveInStart(IntPtr handle);
    [DllImport("winmm.dll")] static extern int waveInReset(IntPtr handle);
    [DllImport("winmm.dll")] static extern int waveInClose(IntPtr handle);
    const int Buffers = 8, Bytes = 1600, Done = 1;  // 0.05 s each

    // "Headphones (Bose QC Ultra 2 HP)" -> "Bose QC Ultra 2 HP"; winmm cuts a name at 31 characters.
    public static string Inner(string name)
    {
        int from = name.IndexOf('('), to = name.LastIndexOf(')');
        return from < 0 ? "" : name.Substring(from + 1, (to > from ? to : name.Length) - from - 1).Trim();
    }

    public static int Find(string output)
    {
        string wanted = Inner(output);
        for (int i = 0; wanted != "" && i < waveInGetNumDevs(); i++)
        {
            var caps = new Caps();
            if (waveInGetDevCapsW((IntPtr)i, ref caps, Marshal.SizeOf(typeof(Caps))) != 0) continue;
            string has = Inner(caps.name);
            if (has != "" && (has.StartsWith(wanted, StringComparison.OrdinalIgnoreCase) || wanted.StartsWith(has, StringComparison.OrdinalIgnoreCase))) return i;
        }
        return -1;
    }

    // Until `stop`. Returns why it could not, or null. `first` runs once, when sound arrives.
    public static string Record(int id, Func<bool> stop, Action first, Action<byte[]> chunk)
    {
        var format = new Format { tag = 1, channels = 1, rate = 16000, bytes = 32000, align = 2, bits = 16 };
        IntPtr handle;
        int result = waveInOpen(out handle, id, ref format, IntPtr.Zero, IntPtr.Zero, 0);
        if (result != 0) return "Windows error " + result;
        int size = Marshal.SizeOf(typeof(Header)), at = 0;
        var headers = new IntPtr[Buffers];
        var buffers = new IntPtr[Buffers];
        for (int i = 0; i < Buffers; i++)
        {
            buffers[i] = Marshal.AllocHGlobal(Bytes);
            headers[i] = Marshal.AllocHGlobal(size);
            Marshal.StructureToPtr(new Header { data = buffers[i], length = Bytes }, headers[i], false);
            waveInPrepareHeader(handle, headers[i], size);
            waveInAddBuffer(handle, headers[i], size);
        }
        waveInStart(handle);
        string error = null;
        bool began = false;
        int last = Environment.TickCount;
        while (!stop())
        {
            var header = (Header)Marshal.PtrToStructure(headers[at], typeof(Header));
            if ((header.flags & Done) == 0)
            {
                if (unchecked(Environment.TickCount - last) > 5000) { error = "no sound came from it"; break; }  // switched off, out of reach
                Thread.Sleep(5);
                continue;
            }
            last = Environment.TickCount;
            var bytes = new byte[header.recorded];
            Marshal.Copy(buffers[at], bytes, 0, header.recorded);
            if (!began) { began = true; first(); }
            if (bytes.Length > 0) chunk(bytes);
            header.flags &= ~Done;
            Marshal.StructureToPtr(header, headers[at], false);
            waveInAddBuffer(handle, headers[at], size);
            at = (at + 1) % Buffers;
        }
        waveInReset(handle);
        for (int i = 0; i < Buffers; i++)
        {
            waveInUnprepareHeader(handle, headers[i], size);
            Marshal.FreeHGlobal(headers[i]);
            Marshal.FreeHGlobal(buffers[i]);
        }
        waveInClose(handle);
        return error;
    }
}

class App : Form
{
    const int KeyApart = 700;  // ms after a media key of the keyboard in which a media button is that key
    delegate IntPtr HookProc(int code, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] static extern IntPtr SetWindowsHookEx(int kind, HookProc proc, IntPtr module, uint thread);
    [DllImport("user32.dll")] static extern bool UnhookWindowsHookEx(IntPtr hook);
    [DllImport("user32.dll")] static extern IntPtr CallNextHookEx(IntPtr hook, int code, IntPtr w, IntPtr l);
    [DllImport("kernel32.dll")] static extern IntPtr GetModuleHandle(string name);

    SystemMediaTransportControls controls;
    GlobalSystemMediaTransportControlsSessionManager media;
    readonly System.Windows.Forms.Timer look = new System.Windows.Forms.Timer { Interval = 1000 };
    readonly HookProc keyProc;
    IntPtr keyHook;
    int keyAt, claimedAt;
    bool holding, overMusic;
    string known = "";
    volatile bool recording, stop;

    App()
    {
        keyProc = OnKey;
        ShowInTaskbar = false;
        look.Tick += delegate { Guard(delegate { Claim(false); }); };
        CreateHandle();
    }

    protected override void SetVisibleCore(bool value) { base.SetVisibleCore(false); }  // only its handle is needed

    static void Guard(Action action)
    {
        try { action(); }
        catch (Exception e) { Out.Send("error", "message", e.GetType().Name + ": " + e.Message); }
    }

    static T Get<T>(Windows.Foundation.IAsyncOperation<T> asked)
    {
        for (int i = 0; i < 3000 && asked.Status == Windows.Foundation.AsyncStatus.Started; i++) Thread.Sleep(10);
        return asked.GetResults();
    }

    // --- the button ----------------------------------------------------------------------------

    IntPtr OnKey(int code, IntPtr w, IntPtr l)
    {
        if (code >= 0)
        {
            int key = Marshal.ReadInt32(l);
            if (key >= 0xB0 && key <= 0xB3) keyAt = Environment.TickCount;  // next, previous, stop, play: a key, not the headset
        }
        return CallNextHookEx(keyHook, code, w, l);
    }

    IEnumerable<GlobalSystemMediaTransportControlsSession> Others()
    {
        return media.GetSessions().Where(x => !x.SourceAppUserModelId.StartsWith("sidetone-headset", StringComparison.OrdinalIgnoreCase));
    }

    static bool Plays(GlobalSystemMediaTransportControlsSession session)
    {
        var info = session.GetPlaybackInfo();
        return info != null && info.PlaybackStatus == GlobalSystemMediaTransportControlsSessionPlaybackStatus.Playing;
    }

    void Hold()
    {
        if (holding) return;
        string output = Output();
        if (output != known) { known = output; LookForDevices(output); }  // other headphones than before
        if (Microphone.Find(output) < 0) { Out.Send("note", "message", "the headphones in use have no microphone; the button is left alone"); return; }
        if (media == null) media = Get(GlobalSystemMediaTransportControlsSessionManager.RequestAsync());
        if (controls == null)
        {
            var interop = (ISmtcInterop)WindowsRuntimeMarshal.GetActivationFactory(typeof(SystemMediaTransportControls));
            var iid = new Guid("99FA3FF4-1742-42A6-902E-087D41F965EC");
            controls = interop.GetForWindow(Handle, ref iid);
            controls.ButtonPressed += (s, e) => { var button = e.Button; BeginInvoke((Action)(() => Guard(() => Pressed(button)))); };
        }
        holding = true;
        keyHook = SetWindowsHookEx(13, keyProc, GetModuleHandle(null), 0);
        Claim(true);
        look.Start();
        Out.Send("held");
    }

    // Windows gives media buttons to one program. With music playing that is the music's unless ours
    // is the newest to say it plays (one that went from paused to playing does not count as new);
    // with none playing, ours says paused, so that a press is Play and a Pause can only be headphones
    // that pause when they are taken off.
    void Claim(bool always)
    {
        if (!holding || recording) return;
        bool music = Others().Any(Plays);
        var current = media.GetCurrentSession();
        bool ours = current != null && current.SourceAppUserModelId.StartsWith("sidetone-headset", StringComparison.OrdinalIgnoreCase);
        if (!always && music == overMusic && (ours || unchecked(Environment.TickCount - claimedAt) < 3000)) return;
        overMusic = music;
        claimedAt = Environment.TickCount;
        controls.PlaybackStatus = MediaPlaybackStatus.Closed;
        controls.IsEnabled = false;
        Thread.Sleep(100);
        controls.IsEnabled = true;
        controls.IsPlayEnabled = controls.IsPauseEnabled = controls.IsNextEnabled = controls.IsPreviousEnabled = true;
        controls.DisplayUpdater.Type = MediaPlaybackType.Music;
        controls.DisplayUpdater.MusicProperties.Title = "Sidetone";
        controls.DisplayUpdater.MusicProperties.Artist = "Press to talk";
        controls.DisplayUpdater.Update();
        controls.PlaybackStatus = music ? MediaPlaybackStatus.Playing : MediaPlaybackStatus.Paused;
    }

    void Release()
    {
        look.Stop();
        if (!holding) return;
        holding = false;
        if (keyHook != IntPtr.Zero) UnhookWindowsHookEx(keyHook);
        keyHook = IntPtr.Zero;
        controls.PlaybackStatus = MediaPlaybackStatus.Closed;
        controls.IsEnabled = false;
        Out.Send("released");
    }

    void Pressed(SystemMediaTransportControlsButton button)
    {
        if (!holding || recording) return;  // as the microphone opens, stray ones come
        bool key = unchecked(Environment.TickCount - keyAt) < KeyApart;
        bool play = button == SystemMediaTransportControlsButton.Play, pause = button == SystemMediaTransportControlsButton.Pause;
        if (!key && (play || (pause && overMusic)))
        {
            Out.Send("press", "button", button.ToString(), ",\"music\":" + (overMusic ? "true" : "false"));
            return;
        }
        if (pause && !key) return;  // headphones taken off
        // The keyboard's key, or two presses: what it would have done without us.
        var other = Others().FirstOrDefault(Plays) ?? Others().FirstOrDefault();
        if (other == null) return;
        if (button == SystemMediaTransportControlsButton.Next) other.TrySkipNextAsync();
        else if (button == SystemMediaTransportControlsButton.Previous) other.TrySkipPreviousAsync();
        else if (play || pause) other.TryTogglePlayPauseAsync();
    }

    // --- the microphone ------------------------------------------------------------------------

    static string Output()
    {
        string id = MediaDevice.GetDefaultAudioRenderId(AudioDeviceRole.Default);
        return string.IsNullOrEmpty(id) ? "" : Get(DeviceInformation.CreateFromIdAsync(id)).Name;
    }

    void Open()
    {
        if (recording) return;
        recording = true;
        stop = false;
        var thread = new Thread(Recording);
        thread.IsBackground = true;
        thread.Start();
    }

    void Recording()
    {
        string error = null;
        try
        {
            string output = Output();
            int id = Microphone.Find(output);
            if (id < 0) error = "the headphones in use have no microphone";
            else error = Microphone.Record(id, () => stop, delegate
            {
                bool call = StartCall();
                Beep(660, 400);
                Out.Send("opened", "device", output, ",\"call\":" + (call ? "true" : "false"));
            }, bytes => Out.Send("audio", "pcm", Convert.ToBase64String(bytes)));
        }
        catch (Exception e) { error = e.GetType().Name + ": " + e.Message; }
        EndCall();
        recording = false;
        Out.Send("closed", "error", error ?? "");
    }

    static void Beep(int pitch, int ms)
    {
        ThreadPool.QueueUserWorkItem(delegate
        {
            try { using (var player = new SoundPlayer(new MemoryStream(Tone(pitch, ms)))) player.PlaySync(); }
            catch (Exception) { }  // no sound is not worth failing over
        });
    }

    static byte[] Tone(int pitch, int ms)
    {
        const int Rate = 22050;
        int count = Rate * ms / 1000;
        var memory = new MemoryStream();
        var w = new BinaryWriter(memory);
        w.Write(Encoding.ASCII.GetBytes("RIFF")); w.Write(36 + count * 2); w.Write(Encoding.ASCII.GetBytes("WAVEfmt ")); w.Write(16);
        w.Write((short)1); w.Write((short)1); w.Write(Rate); w.Write(Rate * 2); w.Write((short)2); w.Write((short)16);
        w.Write(Encoding.ASCII.GetBytes("data")); w.Write(count * 2);
        for (int i = 0; i < count; i++)
            w.Write((short)(7000 * Math.Min(1, Math.Min(i, count - i) / 200.0) * Math.Sin(2 * Math.PI * pitch * i / Rate)));
        w.Flush();
        return memory.ToArray();
    }

    // `pitch`: a tone before it closes, heard at once (what is played after it has to wait for the
    // headphones to switch back, about five seconds).
    void CloseMicrophone(int pitch)
    {
        if (!recording || stop) return;
        Beep(pitch, 250);
        ThreadPool.QueueUserWorkItem(delegate { Thread.Sleep(350); stop = true; });
    }

    // --- the call ------------------------------------------------------------------------------

#if CALLS
    VoipCallCoordinator coordinator;
    VoipPhoneCall call;
    List<string> devices;
    int calledAt;

    [MethodImpl(MethodImplOptions.NoInlining)]
    void FindDevices(string output)  // several seconds
    {
        devices = null;
        string wanted = Microphone.Inner(output);
        if (coordinator == null)
        {
            coordinator = VoipCallCoordinator.GetDefault();
            coordinator.MuteStateChanged += (s, e) =>  // a headset may mute instead of ending; the call's own start says it too
            {
                if (e.Muted && call != null && unchecked(Environment.TickCount - calledAt) > 1500) Out.Send("end", "how", "mute");
            };
        }
        var found = new List<string>();
        foreach (var device in Get(DeviceInformation.FindAllAsync(VoipCallCoordinator.GetDeviceSelectorForCallControl())))
            if (wanted != "" && device.Name != "" && (device.Name.Contains(wanted) || wanted.Contains(device.Name))) found.Add(device.Id);
        devices = found;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    bool StartCall()
    {
        try
        {
            if (devices == null || devices.Count == 0) return false;
            var started = coordinator.RequestNewOutgoingCall("sidetone", "Sidetone", "Sidetone", VoipPhoneCallMedia.Audio);
            started.EndRequested += (s, e) => { Out.Send("end", "how", "call"); EndCall(); };
            calledAt = Environment.TickCount;
            call = started;
            started.NotifyCallActive(devices);
            return true;
        }
        catch (Exception e) { Out.Send("note", "message", "no call: " + e.Message); return false; }
    }

    void EndCall()
    {
        var ended = Interlocked.Exchange(ref call, null);
        if (ended != null) try { ended.NotifyCallEnded(); } catch (Exception) { }
    }

    void LookForDevices(string output)
    {
        ThreadPool.QueueUserWorkItem(delegate
        {
            try { FindDevices(output); Out.Send("note", "message", "call control devices: " + devices.Count); }
            catch (Exception e) { Out.Send("note", "message", "no call control: " + e.Message); }
        });
    }
#else
    bool StartCall() { return false; }
    void EndCall() { }
    void LookForDevices(string output) { }
#endif

    // --- the hub -------------------------------------------------------------------------------

    void Read()
    {
        string line;
        while ((line = Console.In.ReadLine()) != null)
        {
            string word = line.Trim();
            BeginInvoke((Action)(() => Guard(delegate
            {
                if (word == "hold") Hold();
                else if (word == "release") Release();
                else if (word == "open") Open();
                else if (word == "close") CloseMicrophone(880);
                else if (word == "drop") CloseMicrophone(330);
            })));
        }
        BeginInvoke((Action)delegate  // the hub is gone
        {
            stop = true;
            EndCall();
            try { Release(); } catch (Exception) { }
            Application.Exit();
        });
    }

    [STAThread]
    static void Main()
    {
        var app = new App();
        app.known = Output();
        app.LookForDevices(app.known);
        var thread = new Thread(app.Read);
        thread.IsBackground = true;
        thread.Start();
        Out.Send("ready");
        Application.Run();
    }
}
