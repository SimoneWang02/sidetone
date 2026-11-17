# Used by tests/keys_check.py. Presses a spare key the way a held talk key looks to Windows
# (down, repeats, up) and prints which of those presses other programs would still get.
# It watches with a keyboard hook put in before the overlay's own, so anything the overlay
# takes for itself never shows up here. It prints "hooked" once it watches and then waits
# -Delay milliseconds, so the caller can have the overlay put its own hook in after ours.
# With -Modifier (a key such as left Shift, 0xA0) that key is held down first and let go last,
# as the Ctrl and Alt of the real hotkey are, and the output also says whether Windows took it
# for up or down in the middle of the hold.
param([int]$Key = 0x83, [int]$Repeats = 4, [int]$Delay = 300, [int]$Modifier = 0)

Add-Type -ReferencedAssemblies System.Windows.Forms -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

public static class KeysCheck
{
    delegate IntPtr HookProc(int code, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] static extern IntPtr SetWindowsHookEx(int kind, HookProc proc, IntPtr module, uint thread);
    [DllImport("user32.dll")] static extern bool UnhookWindowsHookEx(IntPtr hook);
    [DllImport("user32.dll")] static extern IntPtr CallNextHookEx(IntPtr hook, int code, IntPtr wParam, IntPtr lParam);
    [DllImport("kernel32.dll")] static extern IntPtr GetModuleHandle(string name);
    [DllImport("user32.dll")] static extern void keybd_event(byte key, byte scan, uint flags, UIntPtr extra);
    [DllImport("user32.dll")] static extern short GetAsyncKeyState(int key);

    static readonly List<string> seen = new List<string>();
    static IntPtr hook;
    static int watched;
    static HookProc proc;

    static IntPtr OnKey(int code, IntPtr wParam, IntPtr lParam)
    {
        if (code >= 0 && Marshal.ReadInt32(lParam) == watched)
        {
            int message = wParam.ToInt32();
            lock (seen) seen.Add(message == 0x0100 || message == 0x0104 ? "down" : "up");
        }
        return CallNextHookEx(hook, code, wParam, lParam);
    }

    public static string Run(int key, int repeats, int delay, int modifier)
    {
        watched = key;
        proc = OnKey;
        hook = SetWindowsHookEx(13, proc, GetModuleHandle(null), 0);
        Console.Out.WriteLine("hooked");
        Console.Out.Flush();
        string state = "", held = "";
        var presser = new Thread(delegate() {
            Thread.Sleep(delay);
            if (modifier != 0) { keybd_event((byte)modifier, 0, 0, UIntPtr.Zero); Thread.Sleep(200); }
            keybd_event((byte)key, 0, 0, UIntPtr.Zero);          // the press that starts the hold
            Thread.Sleep(400);                                    // time for the overlay to react
            if (modifier != 0) held = (GetAsyncKeyState(modifier) & 0x8000) != 0 ? "down" : "up";
            for (int i = 0; i < repeats; i++) { keybd_event((byte)key, 0, 0, UIntPtr.Zero); Thread.Sleep(40); }
            keybd_event((byte)key, 0, 2, UIntPtr.Zero);          // let go
            Thread.Sleep(300);
            state = (GetAsyncKeyState(key) & 0x8000) != 0 ? "stuck" : "released";
            keybd_event((byte)key, 0, 0, UIntPtr.Zero);          // a press after the hold is over
            Thread.Sleep(40);
            keybd_event((byte)key, 0, 2, UIntPtr.Zero);
            Thread.Sleep(300);
            if (modifier != 0) { keybd_event((byte)modifier, 0, 2, UIntPtr.Zero); Thread.Sleep(200); }
        });
        presser.Start();
        while (presser.IsAlive) { Application.DoEvents(); Thread.Sleep(2); }
        UnhookWindowsHookEx(hook);
        lock (seen) return string.Join(" ", seen.ToArray()) + " | " + state + (modifier != 0 ? " | " + held : "");
    }
}
"@

[KeysCheck]::Run($Key, $Repeats, $Delay, $Modifier)
