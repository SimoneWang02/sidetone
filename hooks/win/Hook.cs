// Sidetone's hooks on Windows without WSL: one small program, run by Claude Code with the hook's
// name as its argument (exec form, no shell), doing what hooks/*.sh do on Linux and the Mac.
// Claude Code on Windows runs a shell-form hook through Git Bash, or PowerShell when that is
// missing; PowerShell takes about 130 ms to start, this program about 20 (measured on the
// author's PC, 2026-11-24), and it needs no Git. Built by the installer with Windows' own C#
// compiler, as the overlay is, so nothing is downloaded: C# 5, ASCII source.
//
// The hub is reached on 127.0.0.1 at the port written in hub.addr with the token beside it
// (hub/server.py). Usage: sidetone-hook.exe report|report-start|display|speak|notify|permission|stop|listen|reminder
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Management;
using System.Net;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

static class Hook
{
    static readonly UTF8Encoding Utf8 = new UTF8Encoding(false);
    static JavaScriptSerializer json;  // made on first use: loading it is most of a start's time
    static JavaScriptSerializer Json { get { if (json == null) json = new JavaScriptSerializer { MaxJsonLength = int.MaxValue }; return json; } }
    static string Run, State, Home, Root, Python;

    static int Main(string[] args)
    {
        string kind = args.Length > 0 ? args[0] : "";
        Home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        Run = Env("CS_RUN", Path.Combine(local, "sidetone", "run"));
        string input = new StreamReader(Console.OpenStandardInput(), Utf8).ReadToEnd();
        // The two that run at every streamed batch and every tool call leave before anything else
        // is loaded, when there is nothing for them to do (most of the time).
        if (kind == "display" && input.IndexOf("<speak", StringComparison.Ordinal) < 0) return 0;
        if (kind == "stop" && !HasFiles(Path.Combine(Run, "stop")) && !HasFiles(Path.Combine(Run, "steer"))) return 0;
        return Go(kind, input);
    }

    static int Go(string kind, string input)
    {
        State = Env("CS_STATE", Path.Combine(Home, ".local", "state", "sidetone"));
        // Where the checkout and its Python are: written by install.ps1 beside this program.
        var setup = ReadObject(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "hook.json"));
        Root = Env("CS_ROOT", Str(setup, "root"));
        Python = Str(setup, "python");
        if (Python.Length == 0)
            Python = Path.Combine(Env("KOKORO_DIR", Path.Combine(Home, ".local", "share", "kokoro")), "venv", "Scripts", "pythonw.exe");
        ServicePointManager.Expect100Continue = false;
        Console.OutputEncoding = Utf8;
        try
        {
            switch (kind)
            {
                case "display": return Display(input);
                case "report": return Report(input, false);
                case "report-start": return Report(input, true);
                case "speak":
                case "notify": Post("/event", input, 1000); return 0;
                case "permission": return Permission(input);
                case "stop": return Stop(input);
                case "listen": return Listen(input);
                case "reminder": return Reminder();
                default: return 0;
            }
        }
        catch (Exception)
        {
            return 0;  // a hook that fails must never stand in Claude Code's way
        }
    }

    static string Env(string name, string fallback)
    {
        string value = Environment.GetEnvironmentVariable(name);
        return string.IsNullOrEmpty(value) ? fallback : value;
    }

    static Dictionary<string, object> ReadObject(string path)
    {
        try { return Parse(File.ReadAllText(path, Utf8)); }
        catch (Exception) { return new Dictionary<string, object>(); }
    }

    static Dictionary<string, object> Parse(string text)
    {
        try { return Json.Deserialize<Dictionary<string, object>>(text) ?? new Dictionary<string, object>(); }
        catch (Exception) { return new Dictionary<string, object>(); }
    }

    static string Str(Dictionary<string, object> d, string key)
    {
        object v;
        return d != null && d.TryGetValue(key, out v) && v != null ? Convert.ToString(v) : "";
    }

    // MARK: the hub

    static bool Door(out string url, out string token)
    {
        url = token = "";
        try
        {
            string[] parts = File.ReadAllText(Path.Combine(Run, "hub.addr")).Trim().Split(new[] { ' ', '\t', '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length < 2) return false;
            url = "http://127.0.0.1:" + parts[0];
            token = parts[1];
            return true;
        }
        catch (Exception) { return false; }
    }

    // POSTs the hook's payload; the hub's reply, or null when there is no hub or no answer in time.
    static string Post(string path, string body, int milliseconds)
    {
        string url, token;
        if (!Door(out url, out token)) return null;
        try
        {
            var request = (HttpWebRequest)WebRequest.Create(url + path);
            request.Method = "POST";
            request.Proxy = null;
            request.Timeout = request.ReadWriteTimeout = milliseconds;
            request.ContentType = "application/json";
            request.Headers["X-Sidetone-Token"] = token;
            byte[] data = Utf8.GetBytes(body);
            request.ContentLength = data.Length;
            using (Stream s = request.GetRequestStream()) s.Write(data, 0, data.Length);
            using (var response = (HttpWebResponse)request.GetResponse())
            using (var reader = new StreamReader(response.GetResponseStream(), Utf8))
                return reader.ReadToEnd();
        }
        catch (Exception) { return null; }
    }

    // Starts the hub where Claude Code cannot take it down with this hook: through WMI, so it is
    // not a child of the hook (whose job Claude Code may close when the hook ends). A second
    // hub exits by itself (it takes a lock).
    static void StartHub()
    {
        string script = Path.Combine(Root, "hub", "hub.py");
        if (Root.Length == 0 || !File.Exists(script) || !File.Exists(Python)) return;
        Directory.CreateDirectory(Run);
        Directory.CreateDirectory(State);
        string line = "\"" + Python + "\" -I \"" + script + "\"";
        try
        {
            using (var processes = new ManagementClass("Win32_Process"))
            using (var startup = new ManagementClass("Win32_ProcessStartup"))
            {
                startup["ShowWindow"] = (ushort)0;
                var env = new List<string>();
                foreach (string name in new[] { "CS_RUN", "CS_STATE", "CS_ROOT", "KOKORO_DIR", "XDG_CONFIG_HOME", "SIDETONE_TTS", "SIDETONE_OVERLAY" })
                    if (!string.IsNullOrEmpty(Environment.GetEnvironmentVariable(name))) env.Add(name + "=" + Environment.GetEnvironmentVariable(name));
                if (env.Count > 0) startup["EnvironmentVariables"] = env.ToArray();
                var how = processes.GetMethodParameters("Create");
                how["CommandLine"] = line;
                how["CurrentDirectory"] = Root;
                how["ProcessStartupInformation"] = startup;
                processes.InvokeMethod("Create", how, null);
            }
        }
        catch (Exception)
        {
            var info = new ProcessStartInfo(Python, "-I \"" + script + "\"") { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = Root };
            Process.Start(info);
        }
    }

    static bool Up() { string u, t; return Door(out u, out t); }

    // MARK: the hooks

    // Each streamed batch: a line that is a <speak> tag is spoken and shown as its rewrite.
    static int Display(string input)
    {
        if (input.IndexOf("<speak", StringComparison.Ordinal) < 0) return 0;  // the fast way out
        string reply = Post("/display", input, 1000);
        if (reply != null)
        {
            if (reply.Length > 0) Console.Out.Write(reply + "\n");
            return 0;
        }
        StartHub();  // for the next one
        return 0;
    }

    static int Report(string input, bool start)
    {
        if (Post("/event", input, 1000) != null || !start) return 0;
        StartHub();
        for (int i = 0; i < 80; i++)  // the hub needs a moment to open its door; then this event
        {
            Thread.Sleep(100);
            if (Post("/event", input, 1000) != null) break;
        }
        return 0;
    }

    // Holds the prompt open on the hub until it is answered; prints the hub's decision.
    static int Permission(string input)
    {
        if (!Up()) return 0;
        string reply = Post("/permission", input, 3600 * 1000);
        if (!string.IsNullOrEmpty(reply)) Console.Out.Write(reply);
        return 0;
    }

    // Ends the turn when the hub was asked to stop this session; after a step, hands over words
    // spoken to it meanwhile.
    static int Stop(string input)
    {
        string stops = Path.Combine(Run, "stop"), steer = Path.Combine(Run, "steer");
        if (!HasFiles(stops) && !HasFiles(steer)) return 0;
        var payload = Parse(input);
        string session = Str(payload, "session_id"), kind = Str(payload, "hook_event_name");
        if (session.Length == 0 || session.StartsWith(".") || session.IndexOfAny(new[] { '/', '\\' }) >= 0) return 0;
        string stopFile = Path.Combine(stops, session);
        if (TryDelete(stopFile))
        {
            const string told = "The user stopped this turn with the cancel key. Do not go on with it unless they ask.";
            var output = new Dictionary<string, object> { { "continue", false }, { "stopReason", told } };
            if (kind == "PreToolUse")
                output["hookSpecificOutput"] = new Dictionary<string, object> {
                    { "hookEventName", "PreToolUse" }, { "permissionDecision", "deny" }, { "permissionDecisionReason", told } };
            Console.Out.Write(Json.Serialize(output) + "\n");
            return 0;
        }
        if (kind != "PostToolUse") return 0;
        string mine = Path.Combine(steer, session), taken = Path.Combine(steer, "." + session + "." + Process.GetCurrentProcess().Id);
        try { File.Move(mine, taken); } catch (Exception) { return 0; }
        string words = File.ReadAllText(taken, Utf8);
        TryDelete(taken);
        if (words.Length == 0) return 0;
        Console.Out.Write(Json.Serialize(new Dictionary<string, object> { { "hookSpecificOutput",
            new Dictionary<string, object> { { "hookEventName", "PostToolUse" }, { "additionalContext", words } } } }) + "\n");
        return 0;
    }

    static bool HasFiles(string folder)
    {
        try { return Directory.Exists(folder) && Directory.GetFiles(folder).Length > 0; }
        catch (Exception) { return false; }
    }

    static bool TryDelete(string path)
    {
        try
        {
            if (!File.Exists(path)) return false;
            File.Delete(path);
            return true;
        }
        catch (Exception) { return false; }
    }

    // In the background (asyncRewake): waits on the hub for words spoken to this session; prints
    // them for Claude and exits 2, which wakes the session. Released by the hub, it ends quietly.
    static int Listen(string input)
    {
        int wait = 10;
        int.TryParse(Env("CS_WAIT", "10"), out wait);
        for (int i = 0; i < wait * 5 && !Up(); i++) Thread.Sleep(200);
        if (!Up()) return 0;
        double retry = 5;
        double.TryParse(Env("CS_RETRY", "5"), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out retry);
        string reply;
        while ((reply = Post("/listen", input, 86400 * 1000)) == null)
            Thread.Sleep((int)(retry * 1000));  // the hub went away: reachable again once it is back
        string text = Str(Parse(reply), "text");
        if (text.Length == 0) return 0;
        var err = new StreamWriter(Console.OpenStandardError(), Utf8);
        err.Write("The user said this by voice (push-to-talk, transcribed by a local speech model, so a word may be slightly off): \""
                  + text + "\"\nTreat it as their next message: act on it, and reply as usual, starting with the spoken line.\n");
        err.Flush();
        return 2;
    }

    // The instruction each prompt gets (hooks/voice-reminder.sh), from the same settings.
    static int Reminder()
    {
        if (File.Exists(Path.Combine(Home, ".claude", "voice-off"))) return 0;
        string configHome = Env("XDG_CONFIG_HOME", Path.Combine(Home, ".config"));
        var config = ReadObject(Path.Combine(configHome, "sidetone", "config.json"));
        string titles = Str(config, "titles"), language = Str(config, "reply_language");
        if (titles.Length == 0) titles = "ask";
        if (language.Length == 0) language = "spoken";
        string model = Str(config, "whisper_model"), heard = Str(config, "whisper_language");
        if (model.Length == 0) model = "small.en";
        string on;
        if (model.EndsWith(".en")) on = "en";
        else
        {
            var codes = new List<string>();
            bool any = false;
            foreach (string c in (heard.Length > 0 ? heard : "en").ToLowerInvariant().Split(new[] { ',', ' ' }, StringSplitOptions.RemoveEmptyEntries))
            {
                if (c == "auto" || c == "any" || c == "all") any = true;
                codes.Add(c);
            }
            on = any ? "any" : string.Join(",", codes.ToArray());
        }
        var names = new Dictionary<string, string> { { "english", "English" }, { "en", "English" }, { "it", "Italian" }, { "es", "Spanish" },
            { "fr", "French" }, { "pt", "Portuguese" }, { "ja", "Japanese" }, { "zh", "Chinese" }, { "hi", "Hindi" } };
        string name;
        if (!names.TryGetValue(language, out name)) name = "";
        string words;
        if (name == "English") words = "plain spoken English";
        else if (name.Length > 0) words = "plain spoken " + name + " whatever language I used, with lang=\"" + language + "\" in the tag";
        else if (on == "en") words = "plain spoken English whatever language I used";
        else if (on == "any" || on.Length == 0)
            words = "plain spoken words in the language of my last message; when that is not English, also put lang=\"xx\" in the tag with its two-letter code, such as lang=\"it\"";
        else
            words = "plain spoken words in the language of my last message when its two-letter code is one of " + on.Replace(",", ", ")
                    + ", and in English otherwise; when that is not English, also put lang=\"xx\" in the tag with its two-letter code, such as lang=\"it\"";
        if (titles == "auto")
        {
            Console.Out.Write("VOICE MODE: Start your final message (the one after any tool use) with ONE line on its own: <speak>...</speak>, max 2 short sentences, "
                              + words + ", no code, paths, or symbols. Say what you did or what you need from me (a decision, approval, or the next step). Use the tag only for that line; never write it anywhere else.\n");
            return 0;
        }
        Console.Out.Write("VOICE MODE: Start your final message (the one after any tool use) with ONE line on its own: <speak title=\"...\">...</speak>. Inside the tag: max 2 short sentences, "
                          + words + ", no code, paths, or symbols. Say what you did or what you need from me (a decision, approval, or the next step). The title: 2 to 5 plain words that name what this session is working on, such as \"Login page redesign\". It is shown beside the session in a list of sessions, so it must tell this one apart from others in the same project: name the task, not the project and not the last step. Keep the same title from turn to turn and change it only when the work has moved on to something else. Use the tag only for that line; never write it anywhere else.\n");
        return 0;
    }
}
