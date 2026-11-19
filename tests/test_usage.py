"""The plan's usage read from Claude Code's `/usage`, said aloud, asked for by voice; and how
full a session's context is, counted from its record."""
import json
import os
import stat
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hub"))
import usage  # noqa: E402
from usage import Usage, Window  # noqa: E402

# What `claude -p "/usage"` printed on 2026-11-17 (Claude Code 2.1.327), with the folder names
# of the lower part changed. \u00b7 is the raised dot it puts between the parts of a line.
REAL = """You are currently using your subscription to power your Claude Code usage

Current session: 26% used \u00b7 resets Nov 18, 2:39am (America/New_York)
Current week (all models): 38% used \u00b7 resets Nov 23, 7:59am (America/New_York)
Current week (Fable): 73% used \u00b7 resets Nov 23, 7:59am (America/New_York)

What's contributing to your usage?
Approximate \u00b7 sessions on this machine only \u00b7 shares overlap

Last 24h \u00b7 1650 requests \u00b7 37 sessions
  79%  Start fresh when you switch tasks \u00b7 run /clear
  18%  Trim ~/some/project/CLAUDE.md \u00b7 20k tokens per request
  14%  Run fewer sessions at once \u00b7 up to 7 at once
  Top skills: /dataviz 2%, /update-config 1%, /claude-api 1%

Last 7d \u00b7 2170 requests \u00b7 49 sessions
  80%  Start fresh when you switch tasks \u00b7 run /clear
  33%  Review sessions active over many hours \u00b7 whole sessions with requests in 8 or more separate hours
  Top skills: /update-config 2%, /dataviz 2%, /claude-api 1%
"""


class Reading(unittest.TestCase):
    def test_the_real_answer_gives_three_windows(self):
        read = usage.parse(REAL)
        self.assertEqual(read.five_hour, Window(26.0, "Nov 18, 2:39am"))
        self.assertEqual(read.week, Window(38.0, "Nov 23, 7:59am"))
        self.assertEqual(read.models, {"Fable": Window(73.0, "Nov 23, 7:59am")})

    def test_other_dots_spaces_and_line_ends_do_not_matter(self):
        text = "Current session:26 % used - resets 3pm\r\n  Current week (all models): 38.5% used, resets Nov 23\r\n"
        read = usage.parse(text)
        self.assertEqual(read.five_hour, Window(26.0, "3pm"))
        self.assertEqual(read.week, Window(38.5, "Nov 23"))
        self.assertEqual(read.models, {})

    def test_a_line_without_when_still_gives_its_percent(self):
        self.assertEqual(usage.parse("Current session: 4% used").five_hour, Window(4.0, ""))

    def test_a_line_that_does_not_read_is_no_figure(self):
        for line in ("Current session: lots used",
                     "Current session: 26% left \u00b7 resets 3pm",        # not what is used
                     "Current session: 260% used",                         # not a percent of a window
                     "Current session: about 26% used",
                     "Current session 26% used",                           # no colon: not a line of figures
                     "Something new: 26% used \u00b7 resets 3pm",          # a window nobody knows
                     "Current week (a very long name that is no model at all, surely): 5% used",
                     "Current week (rm -rf /): 5% used",
                     "  79%  Start fresh when you switch tasks",
                     "Top skills: /dataviz 2%, /update-config 1%"):
            with self.subTest(line=line):
                self.assertEqual(usage.parse(line), Usage(None, None, {}))
        self.assertEqual(usage.parse(""), Usage(None, None, {}))
        self.assertEqual(usage.parse(None), Usage(None, None, {}))

    def test_one_bad_line_does_not_take_the_others_along(self):
        read = usage.parse(REAL.replace("26% used", "?? used"))
        self.assertIsNone(read.five_hour)
        self.assertEqual(read.week.used, 38.0)
        self.assertEqual(read.models["Fable"].used, 73.0)

    def test_the_first_of_two_lines_for_a_window_counts(self):
        read = usage.parse("Current session: 10% used\nCurrent session: 90% used\n"
                           "Current week (Opus only): 5% used\nCurrent week (Sonnet): 7% used")
        self.assertEqual(read.five_hour.used, 10.0)
        self.assertEqual(sorted(read.models), ["Opus", "Sonnet"])
        self.assertIsNone(read.week)

    def test_other_names_for_the_windows(self):
        read = usage.parse("5-hour limit: 12% used\nSeven day window: 40% used")
        self.assertEqual((read.five_hour.used, read.week.used), (12.0, 40.0))


class Saying(unittest.TestCase):
    def test_the_real_answer_as_a_sentence(self):
        self.assertEqual(usage.say(usage.parse(REAL)),
                         "26 percent of the five hours used, back at 2:39 AM. The week is at 38 percent, Fable at 73.")

    def test_only_plain_words_reach_the_voice(self):
        said = usage.say(usage.parse(REAL))
        self.assertRegex(said, r"\A[A-Za-z0-9 ,.:]+\Z")
        self.assertNotIn("America", said)

    def test_what_is_missing_is_left_out(self):
        five, week, fable = Window(15.0, "2:39am"), Window(37.0, ""), Window(70.0, "")
        self.assertEqual(usage.say(Usage(five, None, {})), "15 percent of the five hours used, back at 2:39 AM.")
        self.assertEqual(usage.say(Usage(Window(15.4, "tomorrow"), None, {})), "15 percent of the five hours used.")
        self.assertEqual(usage.say(Usage(None, week, {})), "The week is at 37 percent.")
        self.assertEqual(usage.say(Usage(None, week, {"Fable": fable})), "The week is at 37 percent, Fable at 70.")
        self.assertEqual(usage.say(Usage(None, None, {"Fable": fable})), "The Fable week is at 70 percent.")
        self.assertEqual(usage.say(Usage(None, None, {"Fable": fable, "Opus": Window(12.0, "")})),
                         "The Fable week is at 70 percent, Opus at 12.")

    def test_nothing_read_is_said_as_such(self):
        for nothing in (Usage(None, None, {}), None, usage.parse("Please log in")):
            self.assertEqual(usage.say(nothing), usage.SORRY)

    def test_the_time_of_day(self):
        for written, spoken in (("Nov 18, 2:39am", "2:39 AM"), ("3pm", "3 PM"), ("Nov 23, 12:05 PM", "12:05 PM"),
                                ("11 a.m.", "11 AM"), ("today 14:30", "14:30"), ("Nov 23", ""), ("in 2 hours", ""),
                                ("", ""), (None, "")):
            with self.subTest(written=written):
                self.assertEqual(usage.clock(written), spoken)


def program(body: str) -> str:
    """A stand-in for the `claude` program: a shell script with this body."""
    folder = tempfile.mkdtemp(prefix="cs-test-")
    path = os.path.join(folder, "claude")
    with open(path, "w") as f:
        f.write("#!/bin/bash\n" + body + "\n")
    os.chmod(path, stat.S_IRWXU)
    return path


class Asking(unittest.TestCase):
    def setUp(self):
        self.cwd = tempfile.mkdtemp(prefix="cs-test-")

    def test_what_the_program_prints_comes_back(self):
        out, why = usage.ask(program("cat <<'END'\n" + REAL + "END"), 5, self.cwd)
        self.assertEqual(why, "")
        self.assertEqual(usage.parse(out).five_hour.used, 26.0)

    def test_how_the_program_is_started(self):
        seen = os.path.join(self.cwd, "seen")
        fake = program(f'printf "%s\\n" "$@" > {seen}.args; env > {seen}.env; pwd > {seen}.cwd; cat > {seen}.stdin; echo ok')
        tied = {"CLAUDE_CODE_SESSION_ID": "abc", "CLAUDECODE": "1", "CLAUDE_PID": "7", "CLAUDE_CODE_SSE_PORT": "1",
                "CLAUDE_CONFIG_DIR": "/somewhere/else"}
        with mock.patch.dict(os.environ, tied):
            started = time.time()
            out, why = usage.ask(fake, 5, self.cwd)
        self.assertEqual((out.strip(), why), ("ok", ""))
        self.assertLess(time.time() - started, 3)  # stdin was closed: nothing waited for it
        with open(seen + ".args") as f:
            args = f.read().split("\n")[:-1]
        self.assertEqual(args[-2:], ["--", "/usage"])
        self.assertIn("-p", args)
        self.assertIn("--no-session-persistence", args)  # leaves no record of a session behind
        self.assertTrue(json.loads(args[args.index("--settings") + 1])["disableAllHooks"])
        with open(seen + ".env") as f:
            names = {line.split("=")[0] for line in f}
        self.assertFalse(names & {"CLAUDE_CODE_SESSION_ID", "CLAUDECODE", "CLAUDE_PID", "CLAUDE_CODE_SSE_PORT"})
        self.assertIn("CLAUDE_CONFIG_DIR", names)  # where the login is kept stays
        with open(seen + ".cwd") as f:
            self.assertEqual(os.path.realpath(f.read().strip()), os.path.realpath(self.cwd))

    def test_no_folder_given_is_one_of_its_own(self):
        run = tempfile.mkdtemp(prefix="cs-test-")
        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": run}):
            out, why = usage.ask(program("pwd"), 5)
        self.assertEqual(os.path.realpath(out.strip()), os.path.realpath(os.path.join(run, "sidetone", "usage")))
        self.assertEqual(stat.S_IMODE(os.stat(out.strip()).st_mode), 0o700)

    def test_a_missing_program(self):
        out, why = usage.ask(os.path.join(self.cwd, "no-such-claude"), 5, self.cwd)
        self.assertEqual(out, "")
        self.assertIn("could not start", why)

    def test_a_program_that_fails(self):
        self.assertEqual(usage.ask(program("echo 'Not logged in' >&2; exit 3"), 5, self.cwd), ("", "Not logged in"))
        self.assertEqual(usage.ask(program("exit 3"), 5, self.cwd), ("", "exit 3"))

    def test_a_program_that_prints_nothing(self):
        self.assertEqual(usage.ask(program("true"), 5, self.cwd), ("", "an empty answer"))

    def test_a_program_that_hangs_is_ended_with_what_it_started(self):
        mark = os.path.join(self.cwd, "child")
        started = time.time()
        out, why = usage.ask(program(f"(sleep 1.5; touch {mark}) & sleep 30"), 0.3, self.cwd)
        self.assertEqual((out, why), ("", "no answer in 0s"))
        self.assertLess(time.time() - started, 3)
        time.sleep(1.6)
        self.assertFalse(os.path.exists(mark))

    def test_the_session_variables_are_the_hubs(self):
        import hub
        self.assertEqual(usage.OWN_SESSION.pattern, hub.OWN_SESSION.pattern)


YES = """
    Alright, so what's the usage?
    All right, what's my usage
    Yeah, how much have I used of the five hours
    what's my usage
    What's my usage?
    What is my usage?
    whats the usage
    What\u2019s the usage right now?
    what's the current usage
    What's my usage like?
    what's the weekly usage
    What's my Fable usage?
    how's my usage looking
    How much usage do I have left?
    how much usage do i have left
    How much usage have I got left?
    how much usage is left
    How much usage is left for this week?
    How much of the five hours have I used?
    how much of the five hours have i used
    How much of the 5-hour window is left?
    How much of the five-hour window have I used so far?
    how much have I used of the five hours
    How much of my plan usage have I used this week?
    How close am I to the usage limit?
    When does the five hours reset?
    When does my usage reset?
    Do I have any usage left?
    Have I used up the five hours?
    check the usage
    Check the usage.
    Check my usage, please.
    check the usage again
    tell me the usage
    Tell me about the usage.
    Give me the usage.
    Show me the usage.
    report the usage
    Can you tell me the usage, please?
    Could you check the usage?
    Hey Claude, what's my usage?
    Okay, so what's the usage?
    By the way, what's my usage?
    usage?
    Usage.
    usage
    Usage, please.
    my usage
    the current usage
    usage check
    plan usage
    What's my use age?
    how much use age do I have left
"""

NO = """
    add a usage meter to the overlay
    Add the usage to the overlay.
    put the usage in the overlay
    show the usage in the overlay
    what's the memory usage of the hub
    What's the memory usage?
    what's the CPU usage
    what's the disk usage of the models
    what's the token usage of this session
    what's the context usage
    how much context have you used
    what's the usage of this function
    What's the usage of the word here?
    check the usage of the function in the hub
    check the usage section in the to-do list
    check that the usage works
    how is the usage read
    how is the usage parsed
    how do I check the usage
    how does the usage command work
    tell me how you read the usage
    tell me about the usage idea
    what did we say about the usage
    what did I say about the usage
    what did the other session find about the usage
    write a test for the usage question
    build the usage feature
    I think it would be great to know the usage
    the usage is at seventy percent so be quick
    I have plenty of usage left so take your time
    we are running out of usage
    what is the usage for
    what's the usage of
    how much have you used
    how much is left
    how much time is left
    five hours
    the five hours
    in five hours
    Give it five hours.
    do I have five hours
    what is five hours in minutes
    wait five hours and try again
    what's the rate limit
    what's the rate limit of the API
    what's the plan
    what's the plan for this week
    how much of the week is left
    check the week
    when does it reset
    use the usage module
    usage meter
    usage in the overlay
    is the usage test passing
    stop
    yes
    alright
    Alright, so use the usage module
    yeah sure

"""


class Recognising(unittest.TestCase):
    def test_questions_about_the_usage(self):
        for said in filter(None, map(str.strip, YES.splitlines())):
            with self.subTest(said=said):
                self.assertTrue(usage.asks(said))

    def test_everything_else_goes_to_the_session(self):
        for said in filter(None, map(str.strip, NO.splitlines())):
            with self.subTest(said=said):
                self.assertFalse(usage.asks(said))
        for said in ("", "   ", "?", None):
            self.assertFalse(usage.asks(said))

    def test_a_long_sentence_is_never_one(self):
        self.assertFalse(usage.asks("what is the usage " + "and the usage " * 5))


def reply(fresh=2, saved=0, reused=0, side=False, model="claude-haiku-5-5"):
    return {"type": "assistant", "isSidechain": side,
            "message": {"model": model, "usage": {"input_tokens": fresh, "cache_creation_input_tokens": saved,
                                                  "cache_read_input_tokens": reused, "output_tokens": 14}}}


def compaction(kept):
    return {"type": "system", "subtype": "compact_boundary", "isSidechain": False,
            "compactMetadata": {"trigger": "manual", "preTokens": 53091, "postTokens": kept}}


class OneTurn(unittest.TestCase):
    def record(self, *entries) -> str:
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        self.addCleanup(os.unlink, path)
        with os.fdopen(fd, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        return path

    @staticmethod
    def reply(id, out, new, again, **more):
        return {"type": "assistant", "message": {"id": id, "usage": {
            "input_tokens": 1, "cache_creation_input_tokens": new - 1, "cache_read_input_tokens": again, "output_tokens": out}}, **more}

    PROMPT = {"type": "user", "message": {"content": "go on"}}
    RESULT = {"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}}

    def test_the_replies_since_the_last_prompt_are_added_up(self):
        path = self.record(self.PROMPT, self.reply("a", 900, 900, 900), self.PROMPT,
                           self.reply("b", 100, 2000, 50000), self.reply("b", 100, 2000, 50000),  # one reply, written twice
                           self.RESULT, self.reply("c", 300, 400, 52000),
                           self.reply("d", 7000, 7000, 7000, isSidechain=True))  # a helper's
        self.assertEqual(usage.turn(path), usage.Turn(400, 2400, 102000, 2))
        self.assertEqual(usage.turn(path).tokens(), 2800)
        self.assertEqual(usage.turn(path).tokens("output"), 400)
        self.assertEqual(usage.turn(path).tokens("all"), 104800)

    def test_from_a_known_place_everything_after_it_counts(self):
        path = self.record(self.PROMPT, self.reply("a", 900, 900, 900))
        start = os.path.getsize(path)
        with open(path, "a") as f:
            f.write(json.dumps(self.reply("b", 100, 2000, 50000)) + "\n" + json.dumps(self.PROMPT) + "\n"
                    + json.dumps(self.reply("c", 300, 400, 52000)) + "\n")  # words handed over in the middle are no new turn
        self.assertEqual(usage.turn(path, start).replies, 2)
        self.assertEqual(usage.turn(path, start + 10_000_000).replies, 1, "a place past the end is not known: the last prompt")

    def test_nothing_to_go_on(self):
        self.assertIsNone(usage.turn("/nonexistent/record.jsonl"))
        self.assertIsNone(usage.turn(self.record(self.PROMPT)))
        self.assertIsNone(usage.turn(self.record(self.PROMPT, {"type": "assistant", "message": "odd"})))

    def test_a_number_of_tokens_in_a_small_place(self):
        self.assertEqual([usage.tokens_text(n) for n in (640, 1234, 9949, 9950, 64400, 999_499, 999_500, 2_469_596)],
                         ["640", "1.2k", "9.9k", "10k", "64k", "999k", "1.0M", "2.5M"])


class HowFull(unittest.TestCase):
    def record(self, *entries) -> str:
        folder = tempfile.mkdtemp(prefix="cs-test-")
        path = os.path.join(folder, "0000-session.jsonl")
        with open(path, "w") as f:
            for entry in entries:
                f.write((entry if isinstance(entry, str) else json.dumps(entry)) + "\n")
        return path

    def test_the_last_reply_says_how_full(self):
        # The figures of the test session of 2026-11-17: 52750 is what /context showed.
        path = self.record({"type": "user", "isSidechain": False}, reply(2, 11434, 25513),
                           {"type": "user", "isSidechain": False}, reply(2, 15750, 36998), reply(2, 15750, 36998),
                           {"type": "system", "subtype": "turn_duration"})
        self.assertEqual(usage.context(path), usage.Context(52750, 1_000_000, 5.275))

    def test_the_window_is_an_argument(self):
        path = self.record(reply(2, 15750, 36998))
        self.assertEqual(usage.context(path, 200_000).percent, 26.375)
        self.assertEqual(usage.context(path, 50_000).percent, 100.0)  # never more than full
        self.assertEqual(usage.context(path, 0).percent, 0.0)

    def test_a_helpers_reply_does_not_count(self):
        path = self.record(reply(2, 15750, 36998), reply(9, 9, 9, side=True))
        self.assertEqual(usage.context(path).tokens, 52750)

    def test_an_error_in_the_models_place_does_not_count(self):
        path = self.record(reply(2, 15750, 36998), reply(0, 0, 0, model="<synthetic>"))
        self.assertEqual(usage.context(path).tokens, 52750)

    def test_a_compaction_after_the_reply_is_the_figure(self):
        path = self.record(reply(2, 15750, 36998), compaction(5892), {"type": "user", "isSidechain": False})
        self.assertEqual(usage.context(path).tokens, 5892)

    def test_a_reply_after_the_compaction_is_the_figure_again(self):
        path = self.record(reply(2, 15750, 36998), compaction(5892), reply(3, 100, 6000))
        self.assertEqual(usage.context(path).tokens, 6103)

    def test_nothing_to_go_on(self):
        self.assertIsNone(usage.context(os.path.join(tempfile.mkdtemp(prefix="cs-test-"), "none.jsonl")))
        self.assertIsNone(usage.context(self.record()))
        self.assertIsNone(usage.context(self.record({"type": "user", "isSidechain": False})))
        self.assertIsNone(usage.context(self.record('{"type": "assistant", broken', "[1, 2]", '"assistant"',
                                                    {"type": "assistant", "message": "text"},
                                                    {"type": "assistant", "message": {"usage": {"input_tokens": "9"}}},
                                                    compaction(None))))

    def test_only_the_end_of_the_record_is_read(self):
        early = reply(1, 1, 1)
        early["padding"] = "x" * 5000
        path = self.record(early, *[{"type": "user", "text": "y" * 500}] * 20, reply(2, 15750, 36998))
        self.assertEqual(usage.context(path, tail=600).tokens, 52750)  # starts in the middle of a line
        with open(path, "a") as f:
            f.write(json.dumps({"type": "user", "text": "z" * 3000}) + "\n")
        self.assertIsNone(usage.context(path, tail=600))  # the reply is further back than was read
        self.assertEqual(usage.context(path).tokens, 52750)

    def test_finding_the_record_of_a_session(self):
        projects = tempfile.mkdtemp(prefix="cs-test-")
        os.makedirs(os.path.join(projects, "-home-me-thing"))
        path = os.path.join(projects, "-home-me-thing", "abc-123.jsonl")
        with open(path, "w") as f:
            f.write(json.dumps(reply(2, 15750, 36998)) + "\n")
        self.assertEqual(usage.transcript(projects, "abc-123"), path)
        self.assertEqual(usage.transcript(projects, "other"), "")
        self.assertEqual(usage.transcript(projects, "*"), "")  # an id is a name, not a pattern
        self.assertEqual(usage.context(usage.transcript(projects, "abc-123")).tokens, 52750)


if __name__ == "__main__":
    unittest.main()
