using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

[assembly: AssemblyTitle("CanvasGate Studio")]
[assembly: AssemblyProduct("CanvasGate Studio")]
[assembly: AssemblyVersion("0.4.1.0")]

internal static class Program
{
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    private static extern int SetCurrentProcessExplicitAppUserModelID(string appId);

    [STAThread]
    private static void Main(string[] args)
    {
        string root = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string data = Path.Combine(root, "CanvasGateStudio");
        if (args.Length == 2 && args[0] == "--data") data = Path.GetFullPath(args[1]);
        bool newInstance;
        using (var instance = new Mutex(true, @"Local\CanvasGateStudio.Desktop", out newInstance))
        {
            if (!newInstance)
            {
                MessageBox.Show("CanvasGate Studio is already open.", "CanvasGate Studio");
                return;
            }
            SetCurrentProcessExplicitAppUserModelID("CanvasGate.Studio");
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new StudioWindow(data));
            instance.ReleaseMutex();
        }
    }
}

internal sealed class StudioWindow : Form
{
    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(IntPtr window, int attribute, ref int value, int size);
    private static readonly Color Graphite = Color.FromArgb(25, 25, 27);
    private readonly string data;
    private readonly string setting;
    private readonly string demo;
    private readonly WebView2 view = new WebView2();
    private readonly Label loading = new Label();
    private Process engine;
    private Uri endpoint;
    private bool switching;
    private bool closedEngine;

    internal StudioWindow(string dataDirectory)
    {
        data = dataDirectory;
        setting = Path.Combine(data, "vault.txt");
        demo = Path.Combine(data, "Demo Vault");
        Text = "CanvasGate Studio";
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        BackColor = Graphite;
        AutoScaleDimensions = new SizeF(96, 96);
        AutoScaleMode = AutoScaleMode.Dpi;
        Size = new Size(1420, 920);
        MinimumSize = new Size(870, 610);
        StartPosition = FormStartPosition.CenterScreen;
        view.Dock = DockStyle.Fill;
        view.DefaultBackgroundColor = Graphite;
        loading.Dock = DockStyle.Fill;
        loading.TextAlign = ContentAlignment.MiddleCenter;
        loading.ForeColor = Color.FromArgb(225, 211, 192);
        loading.BackColor = Graphite;
        loading.Font = new Font("Segoe UI", 13);
        loading.Text = "Opening CanvasGate Studio…";
        Controls.Add(view);
        Controls.Add(loading);
        loading.BringToFront();
        Shown += Initialize;
        FormClosing += CloseEngine;
    }

    private async void Initialize(object sender, EventArgs args)
    {
        switching = true;
        try
        {
            int darkCaption = 1;
            DwmSetWindowAttribute(Handle, 20, ref darkCaption, sizeof(int));
            Rectangle workArea = Screen.FromHandle(Handle).WorkingArea;
            if (Width > workArea.Width || Height > workArea.Height)
            {
                MinimumSize = new Size(Math.Min(MinimumSize.Width, workArea.Width),
                                       Math.Min(MinimumSize.Height, workArea.Height));
                Size = new Size(Math.Min(Width, workArea.Width), Math.Min(Height, workArea.Height));
                Location = new Point(workArea.Left + (workArea.Width - Width) / 2,
                                     workArea.Top + (workArea.Height - Height) / 2);
            }
            Directory.CreateDirectory(data);
            var environment = await CoreWebView2Environment.CreateAsync(null, Path.Combine(data, "WebView2"));
            await view.EnsureCoreWebView2Async(environment);
            var web = view.CoreWebView2;
            web.Settings.AreDevToolsEnabled = false;
            web.Settings.AreDefaultContextMenusEnabled = false;
            web.Settings.IsStatusBarEnabled = false;
            web.NewWindowRequested += (source, request) => request.Handled = true;
            web.NavigationStarting += (source, request) => {
                Uri target;
                request.Cancel = endpoint == null || !Uri.TryCreate(request.Uri, UriKind.Absolute, out target)
                    || endpoint.GetLeftPart(UriPartial.Authority) != target.GetLeftPart(UriPartial.Authority);
            };
            web.WebMessageReceived += ChooseVault;
            web.NavigationCompleted += (source, result) => {
                if (result.IsSuccess) loading.Visible = false;
                else if (!switching) { loading.Visible = true; loading.Text = "CanvasGate could not load this workspace."; }
            };
            string vault = File.Exists(setting) ? File.ReadAllText(setting, Encoding.UTF8).Trim() : demo;
            await OpenVault(Directory.Exists(vault) ? vault : demo);
        }
        catch (WebView2RuntimeNotFoundException)
        {
            loading.Text = "Install Microsoft Edge WebView2 Runtime to open CanvasGate Studio.";
        }
        catch (Exception error)
        {
            loading.Text = "CanvasGate could not start.\n" + error.Message;
        }
        finally { switching = false; }
    }

    private async void ChooseVault(object sender, CoreWebView2WebMessageReceivedEventArgs args)
    {
        if (switching || endpoint == null || args.Source != endpoint.AbsoluteUri || args.TryGetWebMessageAsString() != "choose-vault")
            return;
        using (var picker = new FolderBrowserDialog())
        {
            picker.Description = "Choose an existing Obsidian vault or workflow folder";
            picker.ShowNewFolderButton = false;
            if (picker.ShowDialog(this) != DialogResult.OK) return;
            switching = true;
            bool opened = false;
            try
            {
                loading.Text = "Opening vault…";
                loading.Visible = true;
                await OpenVault(picker.SelectedPath);
                File.WriteAllText(setting, picker.SelectedPath, new UTF8Encoding(false));
                opened = true;
            }
            catch (Exception error)
            {
                MessageBox.Show(this, error.Message, "Could not open vault", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            if (!opened)
            {
                try { await OpenVault(demo); }
                catch { loading.Text = "Could not open the workspace."; }
            }
            switching = false;
        }
    }

    private async Task OpenVault(string vault)
    {
        await StopEngine();
        string python = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "runtime", "python.exe");
        string state = Path.Combine(data, "bridge.json");
        var start = new ProcessStartInfo(python) {
            Arguments = "-I -m canvasgate.desktop --state " + Quote(state) + " --vault " + Quote(vault)
                + (String.Equals(vault, demo, StringComparison.OrdinalIgnoreCase) ? " --demo" : ""),
            UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true,
            RedirectStandardOutput = true, RedirectStandardError = true,
            WorkingDirectory = data
        };
        engine = Process.Start(start);
        engine.BeginErrorReadLine();
        Task<string> result = engine.StandardOutput.ReadLineAsync();
        if (await Task.WhenAny(result, Task.Delay(15000)) != result)
            throw new InvalidOperationException("The local engine timed out.");
        Uri address;
        if (!Uri.TryCreate(await result, UriKind.Absolute, out address) || address.Scheme != "http" || address.Host != "127.0.0.1")
            throw new InvalidOperationException("The local engine did not start. Check the vault path and permissions.");
        endpoint = address;
        view.Source = endpoint;
    }

    private static string Quote(string value)
    {
        return "\"" + value + new String('\\', value.Length - value.TrimEnd('\\').Length) + "\"";
    }

    private async Task StopEngine()
    {
        var process = engine;
        engine = null;
        if (process == null) return;
        process.StandardInput.Close();
        await Task.Run(() => process.WaitForExit());
        process.Dispose();
    }

    private async void CloseEngine(object sender, FormClosingEventArgs args)
    {
        if (closedEngine) return;
        args.Cancel = true;
        if (switching) return;
        switching = true;
        loading.Text = "Closing workspace…";
        loading.Visible = true;
        await StopEngine();
        closedEngine = true;
        Close();
    }
}
