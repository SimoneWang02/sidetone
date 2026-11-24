# Takes the pictures for tests/overlay_check.py. One process for the whole check: it reads one
# JSON request per line and answers each with one JSON line.
#
#   {"do":"window","path":P,"pieces":[[x,y,w,h],...],"process":N}
#       Each piece is a window of the overlay under test (of process N, when given). Its picture is asked from the window
#       itself (PrintWindow), not copied from the screen, so whatever lies over it there, the
#       author's own overlay for one, is not in the picture.
#   {"do":"screen","path":P,"pieces":[...],"pad":N,"ours":[[x,y,w,h],...]}
#       Copied from the screen, for the see-through glass, which only exists on the screen.
#       Answers with "foreign": the always-on-top windows of others that reach into the area,
#       found before and after the copy; a picture with any is not to be kept.
#   {"do":"others","pieces":[...],"pad":N,"ours":[...]}
#       Only that list, without a picture: is this place on the screen free of other programs' windows?
#   {"do":"count","path":P,"color":"#RRGGBB"}   how many dots of a picture have exactly that color
#   {"do":"quit"}
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Text;

public static class Shots
{
    delegate bool EachWindow(IntPtr window, IntPtr unused);
    [DllImport("user32.dll")] static extern bool EnumWindows(EachWindow each, IntPtr unused);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr window);
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr window, out Rect area);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr window, out uint process);
    [DllImport("user32.dll")] static extern bool PrintWindow(IntPtr window, IntPtr context, uint flags);
    [DllImport("user32.dll")] static extern int GetWindowLong(IntPtr window, int index);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassName(IntPtr window, StringBuilder name, int size);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("dwmapi.dll")] static extern int DwmGetWindowAttribute(IntPtr window, int which, out int value, int size);

    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }

    public class Seen
    {
        public IntPtr Handle; public int X, Y, W, H; public uint Process; public bool OnTop; public string Kind;
    }

    // Every window that is really on the screen: shown, with a size, and not put away by Windows.
    public static List<Seen> Windows()
    {
        var found = new List<Seen>();
        EnumWindows(delegate(IntPtr window, IntPtr unused)
        {
            Rect r; int cloaked; uint process;
            if (!IsWindowVisible(window) || !GetWindowRect(window, out r)) return true;
            if (r.Right <= r.Left || r.Bottom <= r.Top) return true;
            if (DwmGetWindowAttribute(window, 14, out cloaked, 4) == 0 && cloaked != 0) return true;
            GetWindowThreadProcessId(window, out process);
            var name = new StringBuilder(200);
            GetClassName(window, name, 200);
            found.Add(new Seen { Handle = window, X = r.Left, Y = r.Top, W = r.Right - r.Left, H = r.Bottom - r.Top, Process = process,
                                 OnTop = (GetWindowLong(window, -20) & 8) != 0, Kind = name.ToString() });
            return true;
        }, IntPtr.Zero);
        return found;
    }

    // What a window itself draws, whatever covers it on the screen. Null if Windows will not say.
    public static Bitmap Of(IntPtr window, int w, int h)
    {
        var picture = new Bitmap(w, h, PixelFormat.Format32bppArgb);
        bool done;
        using (Graphics g = Graphics.FromImage(picture))
        {
            IntPtr context = g.GetHdc();
            done = PrintWindow(window, context, 2);  // 2: the whole content as the screen composer has it
            g.ReleaseHdc(context);
        }
        if (!done) { picture.Dispose(); return null; }
        return picture;
    }

    public static int Count(Bitmap picture, Color wanted)
    {
        int n = 0;
        for (int y = 0; y < picture.Height; y++)
            for (int x = 0; x < picture.Width; x++)
            {
                Color c = picture.GetPixel(x, y);
                if (c.R == wanted.R && c.G == wanted.G && c.B == wanted.B) n++;
            }
        return n;
    }
}
'@
[void][Shots]::SetProcessDPIAware()  # so that places on the screen mean the same here as in the overlay

function Reply($answer) { [Console]::Out.WriteLine(($answer | ConvertTo-Json -Compress -Depth 6)); [Console]::Out.Flush() }

function Same($w, $p) { return $w.X -eq $p[0] -and $w.Y -eq $p[1] -and $w.W -eq $p[2] -and $w.H -eq $p[3] }

function Touches($w, $x0, $y0, $x1, $y1) { return $w.X -lt $x1 -and ($w.X + $w.W) -gt $x0 -and $w.Y -lt $y1 -and ($w.Y + $w.H) -gt $y0 }

# Always-on-top windows that reach into an area and are none of ours.
function Foreign($x0, $y0, $x1, $y1, $ours) {
  $list = @()
  foreach ($w in [Shots]::Windows()) {
    if (-not $w.OnTop -or -not (Touches $w $x0 $y0 $x1 $y1)) { continue }
    $mine = $false
    foreach ($o in $ours) { if (Same $w $o) { $mine = $true } }
    if (-not $mine) {
      $who = ''
      try { $who = (Get-Process -Id $w.Process -ErrorAction Stop).ProcessName } catch { }
      $list += ,@{ process = $who; kind = $w.Kind; area = @($w.X, $w.Y, $w.W, $w.H) }
    }
  }
  return ,$list
}

Reply @{ ready = $true }
while ($null -ne ($line = [Console]::In.ReadLine())) {
  if (-not $line.Trim()) { continue }
  try {
    $ask = $line | ConvertFrom-Json
    if ($ask.do -eq 'quit') { break }
    if ($ask.do -eq 'count') {
      $picture = New-Object System.Drawing.Bitmap $ask.path
      $n = [Shots]::Count($picture, [System.Drawing.ColorTranslator]::FromHtml($ask.color))
      $size = $picture.Width * $picture.Height
      $picture.Dispose()
      Reply @{ ok = $true; count = $n; of = $size }
      continue
    }
    $pieces = @($ask.pieces | ForEach-Object { ,@([int]$_[0], [int]$_[1], [int]$_[2], [int]$_[3]) })
    $pad = if ($ask.pad) { [int]$ask.pad } else { 0 }
    $x0 = ($pieces | ForEach-Object { $_[0] } | Measure-Object -Minimum).Minimum - $pad
    $y0 = ($pieces | ForEach-Object { $_[1] } | Measure-Object -Minimum).Minimum - $pad
    $x1 = ($pieces | ForEach-Object { $_[0] + $_[2] } | Measure-Object -Maximum).Maximum + $pad
    $y1 = ($pieces | ForEach-Object { $_[1] + $_[3] } | Measure-Object -Maximum).Maximum + $pad
    if ($ask.do -eq 'others') {
      $ours = @($ask.ours | ForEach-Object { ,@([int]$_[0], [int]$_[1], [int]$_[2], [int]$_[3]) })
      $there = Foreign $x0 $y0 $x1 $y1 $ours
      Reply @{ ok = $true; foreign = @($there) }
      continue
    }
    $whole = New-Object System.Drawing.Bitmap ([int]($x1 - $x0)), ([int]($y1 - $y0))
    $g = [System.Drawing.Graphics]::FromImage($whole)
    $g.Clear([System.Drawing.Color]::Black)
    $answer = @{ ok = $true }
    if ($ask.do -eq 'window') {
      $all = [Shots]::Windows()
      foreach ($p in $pieces) {
        # Only the overlay's own when it is known: a maximized window has the place of the
        # desktop itself (Progman) and of full-screen windows such as NVIDIA's overlay.
        $found = @($all | Where-Object { (Same $_ $p) -and (-not $ask.process -or $_.Process -eq [uint32]$ask.process) })
        if ($found.Count -ne 1) { $answer = @{ ok = $false; error = "$($found.Count) windows are exactly at $($p -join ',')" }; break }
        $one = [Shots]::Of($found[0].Handle, $p[2], $p[3])
        if ($null -eq $one) { $answer = @{ ok = $false; error = "Windows gave no picture of the window at $($p -join ',')" }; break }
        $g.DrawImageUnscaled($one, $p[0] - $x0, $p[1] - $y0)
        $one.Dispose()
      }
    } else {
      $ours = @($ask.ours | ForEach-Object { ,@([int]$_[0], [int]$_[1], [int]$_[2], [int]$_[3]) })
      $before = Foreign $x0 $y0 $x1 $y1 $ours
      $g.CopyFromScreen([int]$x0, [int]$y0, 0, 0, (New-Object System.Drawing.Size ([int]($x1 - $x0)), ([int]($y1 - $y0))))
      $after = Foreign $x0 $y0 $x1 $y1 $ours
      $answer.foreign = @($before) + @($after)
    }
    $g.Dispose()
    if ($answer.ok) { $whole.Save($ask.path, [System.Drawing.Imaging.ImageFormat]::Png) }
    $whole.Dispose()
    $answer.area = @([int]$x0, [int]$y0, [int]($x1 - $x0), [int]($y1 - $y0))
    Reply $answer
  } catch {
    Reply @{ ok = $false; error = "$_" }
  }
}
