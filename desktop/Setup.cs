using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("CanvasGate Studio Setup")]
[assembly: AssemblyProduct("CanvasGate Studio")]
[assembly: AssemblyVersion("0.4.1.0")]

internal static class Setup
{
    private const string Product = "CanvasGate Studio";
    private const string RegistryKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\CanvasGateStudio";
    private static readonly string Programs = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs");
    private static readonly string Install = Path.Combine(Programs, Product);
    private static readonly string Uninstaller = Path.Combine(Install, "Uninstall.exe");
    private static readonly string Executable = Path.Combine(Install, "CanvasGate Studio.exe");
    private static readonly string DesktopLink = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), Product + ".lnk");
    private static readonly string StartLink = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), Product + ".lnk");
    private static readonly byte[] Signature = Encoding.ASCII.GetBytes("CANVASGATE_SETUP_04");

    [STAThread]
    private static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        bool silent = Array.IndexOf(args, "--quiet") >= 0;
        try
        {
            if (args.Length == 2 && args[0] == "--remove-after")
            {
                int pid = Int32.Parse(args[1]);
                try { Process.GetProcessById(pid).WaitForExit(15000); } catch (ArgumentException) { }
                Remove();
                MessageBox.Show("CanvasGate Studio was removed. Vaults and run history were kept.", Product);
                return 0;
            }
#if UNINSTALL
            if (MessageBox.Show("Remove CanvasGate Studio? Vaults and run history will be kept.", Product,
                MessageBoxButtons.OKCancel, MessageBoxIcon.Question) == DialogResult.OK)
            {
                CheckClosed();
                string copy = Path.Combine(Path.GetTempPath(), "CanvasGate-Uninstall-" + Guid.NewGuid().ToString("N") + ".exe");
                File.Copy(Application.ExecutablePath, copy);
                Process.Start(copy, "--remove-after " + Process.GetCurrentProcess().Id);
            }
#else
            if (!silent && MessageBox.Show("Install CanvasGate Studio for your Windows account?\n\nSetup creates Desktop and Start menu shortcuts.", Product,
                MessageBoxButtons.OKCancel, MessageBoxIcon.Question) != DialogResult.OK) return 0;
            InstallPackage();
            if (!silent && MessageBox.Show("CanvasGate Studio is installed. Open it now?", Product,
                MessageBoxButtons.YesNo, MessageBoxIcon.Information) == DialogResult.Yes)
                Process.Start(Executable);
#endif
            return 0;
        }
        catch (Exception error)
        {
            if (silent) File.WriteAllText(Path.Combine(Path.GetTempPath(), "CanvasGate-Setup-error.txt"), error.Message);
            else MessageBox.Show(error.Message, Product, MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    private static void CheckClosed()
    {
        Mutex running;
        if (!Mutex.TryOpenExisting(@"Local\CanvasGateStudio.Desktop", out running)) return;
        using (running) throw new InvalidOperationException("Close CanvasGate Studio before continuing.");
    }

    private static void InstallPackage()
    {
        CheckClosed();
        Directory.CreateDirectory(Programs);
        string work = Path.Combine(Programs, "CanvasGateSetup-" + Guid.NewGuid().ToString("N"));
        string stage = Path.Combine(work, "app");
        string backup = Path.Combine(work, "backup");
        Directory.CreateDirectory(work);
        bool updated = false;
        try
        {
            string archive = Path.Combine(work, "payload.zip");
            ExtractPayload(archive);
            ZipFile.ExtractToDirectory(archive, stage);
            if (!File.Exists(Path.Combine(stage, "CanvasGate Studio.exe")) || !File.Exists(Path.Combine(stage, "Uninstall.exe")))
                throw new InvalidDataException("The installer payload is incomplete.");
            if (Directory.Exists(Install))
            {
                VerifyInstall();
                Directory.Move(Install, backup);
            }
            try
            {
                Directory.Move(stage, Install);
                CreateShortcut(DesktopLink);
                CreateShortcut(StartLink);
                using (var key = Registry.CurrentUser.CreateSubKey(RegistryKey))
                {
                    key.SetValue("DisplayName", Product);
                    key.SetValue("DisplayVersion", "0.4.1");
                    key.SetValue("Publisher", "CanvasGate");
                    key.SetValue("InstallLocation", Install);
                    key.SetValue("DisplayIcon", Executable);
                    key.SetValue("UninstallString", "\"" + Uninstaller + "\"");
                    key.SetValue("NoModify", 1, RegistryValueKind.DWord);
                    key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
                }
                updated = true;
            }
            finally
            {
                if (!updated && !Directory.Exists(stage))
                {
                    Directory.Move(Install, stage);
                    if (!Directory.Exists(backup))
                    {
                        File.Delete(DesktopLink);
                        File.Delete(StartLink);
                        Registry.CurrentUser.DeleteSubKeyTree(RegistryKey, false);
                    }
                }
                if (!updated && Directory.Exists(backup)) Directory.Move(backup, Install);
            }
        }
        finally
        {
            if (updated || !Directory.Exists(backup)) Directory.Delete(work, true);
        }
    }

    private static void ExtractPayload(string archive)
    {
        using (var input = File.OpenRead(Application.ExecutablePath))
        using (var reader = new BinaryReader(input, Encoding.ASCII))
        {
            input.Seek(-Signature.Length - sizeof(long), SeekOrigin.End);
            long bytes = reader.ReadInt64();
            if (bytes < 1 || bytes > input.Length - Signature.Length - sizeof(long) ||
                !StructuralEquals(reader.ReadBytes(Signature.Length), Signature))
                throw new InvalidDataException("Setup package is damaged.");
            input.Seek(-Signature.Length - sizeof(long) - bytes, SeekOrigin.End);
            using (var output = File.Create(archive))
            {
                var buffer = new byte[65536];
                while (bytes > 0)
                {
                    int read = input.Read(buffer, 0, (int)Math.Min(bytes, buffer.Length));
                    if (read == 0) throw new EndOfStreamException();
                    output.Write(buffer, 0, read);
                    bytes -= read;
                }
            }
        }
    }

    private static bool StructuralEquals(byte[] a, byte[] b)
    {
        if (a.Length != b.Length) return false;
        for (int i = 0; i != a.Length; ++i) if (a[i] != b[i]) return false;
        return true;
    }

    private static void CreateShortcut(string path)
    {
        var shell = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
        object link = null;
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            link = shell.GetType().InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] {path});
            var type = link.GetType();
            type.InvokeMember("TargetPath", BindingFlags.SetProperty, null, link, new object[] {Executable});
            type.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, link, new object[] {Install});
            type.InvokeMember("IconLocation", BindingFlags.SetProperty, null, link, new object[] {Executable + ",0"});
            type.InvokeMember("Description", BindingFlags.SetProperty, null, link, new object[] {Product});
            type.InvokeMember("Save", BindingFlags.InvokeMethod, null, link, null);
        }
        finally
        {
            if (link != null) Marshal.FinalReleaseComObject(link);
            Marshal.FinalReleaseComObject(shell);
        }
    }

    private static void VerifyInstall()
    {
        if ((File.GetAttributes(Install) & FileAttributes.ReparsePoint) != 0 || !File.Exists(Uninstaller) || !File.Exists(Executable))
            throw new InvalidOperationException("The installation directory is already used by another application.");
    }

    private static void Remove()
    {
        CheckClosed();
        VerifyInstall();
        Directory.Delete(Install, true);
        File.Delete(DesktopLink);
        File.Delete(StartLink);
        Registry.CurrentUser.DeleteSubKeyTree(RegistryKey, false);
    }
}
