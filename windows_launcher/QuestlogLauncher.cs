using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Threading;
using System.Windows.Forms;

internal static class QuestlogLauncher
{
    private const string Url = "http://127.0.0.1:8765";
    private const string HealthUrl = "http://127.0.0.1:8765/api/health";

    [STAThread]
    private static void Main()
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;

        if (!ServerIsReady())
        {
            string starter = Path.Combine(root, "START_APP.bat");

            if (!File.Exists(starter))
            {
                MessageBox.Show(
                    "START_APP.bat was not found next to the launcher.",
                    "Questlog TL Farm Planner",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
                return;
            }

            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = "cmd.exe";
                psi.Arguments = "/d /s /c \"\"" + starter + "\"\"";
                psi.WorkingDirectory = root;
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                psi.WindowStyle = ProcessWindowStyle.Hidden;
                Process.Start(psi);
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "Could not start the planner:\r\n\r\n" + ex.Message,
                    "Questlog TL Farm Planner",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
                return;
            }

            for (int i = 0; i < 60 && !ServerIsReady(); i++)
            {
                Thread.Sleep(500);
            }
        }

        if (!ServerIsReady())
        {
            MessageBox.Show(
                "The planner server did not become ready within 30 seconds.\r\n\r\n" +
                "Run START_APP.bat once to see the server error.",
                "Questlog TL Farm Planner",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return;
        }

        try
        {
            ProcessStartInfo browser = new ProcessStartInfo();
            browser.FileName = Url;
            browser.UseShellExecute = true;
            Process.Start(browser);
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                "The planner started, but Windows could not open the browser:\r\n\r\n" + ex.Message,
                "Questlog TL Farm Planner",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning
            );
        }
    }

    private static bool ServerIsReady()
    {
        try
        {
            HttpWebRequest request = (HttpWebRequest)WebRequest.Create(HealthUrl);
            request.Method = "GET";
            request.Timeout = 900;
            request.ReadWriteTimeout = 900;
            request.Proxy = null;

            using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
            {
                return (int)response.StatusCode >= 200 && (int)response.StatusCode < 300;
            }
        }
        catch
        {
            return false;
        }
    }
}
