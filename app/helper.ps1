# Tatami Room app helper: brings a window to the front by its handle, so clicking a mat doesn't
# have to go through WSL. The app starts it once and keeps it running. Each line it reads is
# "<request id> <window handle>"; it answers "<request id> <result>": 0 in front, 1 shown but
# Windows kept the focus elsewhere, 2 not a window (any more).
Add-Type @"
using System; using System.Runtime.InteropServices;
public class TatamiFront {
  [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
  [DllImport("user32.dll")] static extern bool IsWindow(IntPtr h);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h, int n);
  [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr pid);
  [DllImport("user32.dll")] static extern bool AttachThreadInput(uint a, uint b, bool attach);
  [DllImport("user32.dll")] static extern bool BringWindowToTop(IntPtr h);
  [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
  public static int Focus(long handle) {
    IntPtr w = new IntPtr(handle);
    if (!IsWindow(w) || !IsWindowVisible(w)) return 2;
    if (IsIconic(w)) ShowWindow(w, 9);          // restore it if it's minimized
    uint front = GetWindowThreadProcessId(GetForegroundWindow(), IntPtr.Zero), me = GetCurrentThreadId();
    AttachThreadInput(front, me, true);         // sharing input with the window in front lets
    BringWindowToTop(w);                        // us hand the focus over
    SetForegroundWindow(w);
    AttachThreadInput(front, me, false);
    return GetForegroundWindow() == w ? 0 : 1;
  }
}
"@
while ($null -ne ($line = [Console]::In.ReadLine())) {
  $id, $handle = $line.Trim() -split '\s+', 2
  $rc = 2
  try { $rc = [TatamiFront]::Focus([long]$handle) } catch { }
  [Console]::Out.WriteLine("$id $rc")
  [Console]::Out.Flush()
}
