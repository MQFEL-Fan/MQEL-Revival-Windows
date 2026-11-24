# Launcher background: puts a picture into the torn-paper frame of the
# original launcher background (822x600, served at /launcher/background.png,
# patcher.BACKGROUND). Writes 5 candidates plus previews (login box, news
# box, progress bar drawn on top) into launcher-mockups\ for review.
#   powershell -ExecutionPolicy Bypass -File tools\launcher_background.ps1 -Art <image>
# The frame comes from launcher-mockups\frame.png (a copy of the original
# DefaultBackground.png, made on the first run), so the script still works
# after a candidate replaced client\Launcher\DefaultBackground.png.
param(
    [Parameter(Mandatory = $true)][string]$Art,
    [string]$Out = ''
)
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Out) { $Out = Join-Path $Here '..\launcher-mockups' }
New-Item -ItemType Directory -Force $Out | Out-Null
$Out = (Resolve-Path $Out).Path
$FramePath = Join-Path $Out 'frame.png'
if (-not (Test-Path $FramePath)) {
    Copy-Item (Join-Path $Here '..\client\Launcher\DefaultBackground.png') $FramePath
}
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'
using System;
using System.IO;
using System.Drawing;
using System.Drawing.Imaging;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;

public static class LauncherBg {
    static byte[] Lock(Bitmap b, out BitmapData d) {
        d = b.LockBits(new Rectangle(0, 0, b.Width, b.Height), ImageLockMode.ReadWrite, PixelFormat.Format32bppArgb);
        byte[] a = new byte[d.Stride * b.Height];
        Marshal.Copy(d.Scan0, a, 0, a.Length);
        return a;
    }
    static void Unlock(Bitmap b, BitmapData d, byte[] a) { Marshal.Copy(a, 0, d.Scan0, a.Length); b.UnlockBits(d); }

    static Bitmap Scene(Image art, RectangleF src, int w, int h) {
        Bitmap s = new Bitmap(w, h, PixelFormat.Format32bppArgb);
        using (Graphics g = Graphics.FromImage(s)) {
            g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            g.PixelOffsetMode = PixelOffsetMode.HighQuality;
            g.DrawImage(art, new RectangleF(0, 0, w, h), src, GraphicsUnit.Pixel);
        }
        return s;
    }

    static Bitmap Blur(Bitmap s, int f) {
        Bitmap small = new Bitmap(Math.Max(1, s.Width / f), Math.Max(1, s.Height / f));
        using (Graphics g = Graphics.FromImage(small)) {
            g.InterpolationMode = InterpolationMode.HighQualityBilinear;
            g.DrawImage(s, 0, 0, small.Width, small.Height);
        }
        Bitmap big = new Bitmap(s.Width, s.Height, PixelFormat.Format32bppArgb);
        using (Graphics g = Graphics.FromImage(big)) {
            g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            g.DrawImage(small, -f, -f, s.Width + 2 * f, s.Height + 2 * f);
        }
        small.Dispose();
        return big;
    }

    // soft focus right of x0 (fading in over 90 px)
    static void SoftRight(Bitmap s, int x0) {
        Bitmap soft = Blur(s, 6);
        BitmapData d1, d2; byte[] a = Lock(s, out d1), b = Lock(soft, out d2);
        for (int y = 0; y < s.Height; y++) for (int x = x0; x < s.Width; x++) {
            double t = Math.Min(1.0, (x - x0) / 90.0);
            int i = y * d1.Stride + x * 4;
            for (int c = 0; c < 3; c++) a[i + c] = (byte)(a[i + c] * (1 - t) + b[i + c] * t);
        }
        Unlock(s, d1, a); soft.UnlockBits(d2); soft.Dispose();
    }

    // shade: darker right of x0 (behind the login column); tint: towards the
    // frame's teal; vignette: darker edges
    static void Grade(Bitmap s, int x0, double shade, double tint, double vignette) {
        BitmapData d; byte[] a = Lock(s, out d);
        int w = s.Width, h = s.Height;
        double[] teal = { 123, 91, 8 };  // B, G, R
        for (int y = 0; y < h; y++) for (int x = 0; x < w; x++) {
            int i = y * d.Stride + x * 4;
            double k = 1.0;
            if (shade > 0 && x > x0) k *= 1.0 - shade * Math.Min(1.0, (x - x0) / 120.0);
            if (vignette > 0) {
                double dx = (x - w / 2.0) / (w / 2.0), dy = (y - h / 2.0) / (h / 2.0);
                k *= 1.0 - vignette * Math.Min(1.0, Math.Max(0.0, (dx * dx + dy * dy - 0.35) / 1.2));
            }
            for (int c = 0; c < 3; c++) {
                double v = a[i + c] * (1 - tint) + teal[c] * tint * (a[i + c] / 255.0 + 0.5);
                a[i + c] = (byte)Math.Max(0, Math.Min(255, v * k));
            }
        }
        Unlock(s, d, a);
    }

    // dark band behind the launcher's version line (LocalLauncher footer:
    // white 10 px text without shadow, bottom-left, y ~536-552): fades in
    // from y0, full from y0 + 14
    static void FooterBand(Bitmap s, int y0, double dark) {
        BitmapData d; byte[] a = Lock(s, out d);
        for (int y = y0; y < s.Height; y++) {
            double k = 1.0 - dark * Math.Min(1.0, (y - y0) / 14.0);
            for (int x = 0; x < s.Width; x++) {
                int i = y * d.Stride + x * 4;
                for (int c = 0; c < 3; c++) a[i + c] = (byte)(a[i + c] * k);
            }
        }
        Unlock(s, d, a);
    }

    // frame pixels kept (black outline, shadow, transparency), teal inside replaced
    static Bitmap Frame(Bitmap frame, Bitmap scene) {
        Bitmap o = new Bitmap(frame.Width, frame.Height, PixelFormat.Format32bppArgb);
        using (Graphics g = Graphics.FromImage(o)) g.DrawImage(frame, new Rectangle(0, 0, frame.Width, frame.Height));  // not Unscaled: DPI
        BitmapData fd, sd; byte[] f = Lock(o, out fd), s = Lock(scene, out sd);
        for (int i = 0; i < f.Length; i += 4) {
            if (f[i + 3] < 255) continue;
            double t = Math.Max(0.0, Math.Min(1.0, (f[i] - 12) / 36.0));   // blue: outline 0, teal 60-123
            for (int c = 0; c < 3; c++) f[i + c] = (byte)(f[i + c] * (1 - t) + s[i + c] * t);
        }
        Unlock(o, fd, f); scene.UnlockBits(sd);
        return o;
    }

    static GraphicsPath Round(RectangleF r, float rad) {
        GraphicsPath p = new GraphicsPath();
        p.AddArc(r.X, r.Y, rad * 2, rad * 2, 180, 90);
        p.AddArc(r.Right - rad * 2, r.Y, rad * 2, rad * 2, 270, 90);
        p.AddArc(r.Right - rad * 2, r.Bottom - rad * 2, rad * 2, rad * 2, 0, 90);
        p.AddArc(r.X, r.Bottom - rad * 2, rad * 2, rad * 2, 90, 90);
        p.CloseFigure();
        return p;
    }

    // what the launcher draws on top (patcher.LOGIN_PAGE: #col top 56, right
    // 48, width 326; the launcher's progress bar and version line)
    static Bitmap Preview(Bitmap bg) {
        Bitmap o = new Bitmap(bg.Width, bg.Height, PixelFormat.Format32bppArgb);
        using (Graphics g = Graphics.FromImage(o)) {
            g.Clear(Color.FromArgb(70, 70, 70));   // desktop behind the window
            g.DrawImage(bg, new Rectangle(0, 0, bg.Width, bg.Height));
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAlias;
            Brush box = new SolidBrush(Color.FromArgb(209, 18, 14, 34));
            Pen edge = new Pen(Color.FromArgb(46, 255, 255, 255));
            Font f = new Font("Arial", 10f), big = new Font("Arial", 11f), fb = new Font("Arial", 10f, FontStyle.Bold);
            RectangleF login = new RectangleF(448, 56, 326, 190), news = new RectangleF(448, 258, 326, 172);
            foreach (RectangleF r in new RectangleF[] { login, news }) { g.FillPath(box, Round(r, 8)); g.DrawPath(edge, Round(r, 8)); }
            g.FillRectangle(new SolidBrush(Color.FromArgb(88, 101, 242)), 470, 76, 68, 20);
            g.DrawString("Discord", f, Brushes.White, 478, 78);
            g.FillRectangle(Brushes.White, 626, 76, 126, 22);
            g.DrawString("English", f, Brushes.Black, 632, 79);
            g.DrawString("Logged in as Player.", big, new SolidBrush(Color.FromArgb(153, 255, 153)), 470, 112);
            g.DrawString("Press Play to start the game.", big, Brushes.Gainsboro, 470, 146);
            g.FillRectangle(Brushes.White, 470, 194, 78, 30);
            g.DrawString("Log out", big, Brushes.Black, 482, 200);
            g.DrawString("2026-11-21  Castle upgrades for level 60", fb, Brushes.White, 470, 290);
            g.DrawString("Craft Goldmaw the Insatiable, more rooms,\nbigger mines, defense rating 750 ...", f, Brushes.Gainsboro, 470, 312);
            g.FillRectangle(new SolidBrush(Color.FromArgb(220, 10, 20, 30)), 100, 502, 226, 20);
            g.FillRectangle(new SolidBrush(Color.FromArgb(180, 210, 235)), 101, 503, 72, 18);
            g.DrawString("Verifying files ...", new Font("Arial", 8f), Brushes.White, 242, 506);
            g.DrawString("0.36.1.34.0-mqel-live - launcher #276072 [STEAM] - binary #280139 - data #104956",
                         new Font("Arial", 7f), Brushes.Gainsboro, 14, 540);
        }
        return o;
    }

    // name, center x, center y, source height (art pixels), shade, tint, vignette, soft right half
    public static void Run(string artPath, string framePath, string outDir) {
        using (Image art = Image.FromFile(artPath))
        using (Bitmap frame = new Bitmap(framePath)) {
            int w = frame.Width, h = frame.Height;
            double aspect = (double)w / h;
            object[][] variants = {
                new object[] { "1-cover",            960.0, 540.0, 1040.0, 0.0,  0.0,  0.25, false },
                new object[] { "2-cover-shaded",     960.0, 540.0, 1040.0, 0.55, 0.0,  0.30, false },
                new object[] { "3-logo-left",        1180.0, 520.0, 980.0, 0.45, 0.0,  0.30, false },
                new object[] { "4-teal-tint",        960.0, 540.0, 1040.0, 0.35, 0.35, 0.35, false },
                new object[] { "5-logo-close-soft", 1230.0, 470.0, 860.0, 0.50, 0.10, 0.30, true },
                new object[] { "6-logo-close",      1230.0, 470.0, 860.0, 0.0,  0.0,  0.0,  false },  // chosen 2026-11-21: 5 without blur/shading
            };
            foreach (object[] v in variants) {
                double sh = (double)v[3], sw = sh * aspect;
                RectangleF src = new RectangleF((float)((double)v[1] - sw / 2), (float)((double)v[2] - sh / 2), (float)sw, (float)sh);
                using (Bitmap scene = Scene(art, src, w, h)) {
                    if ((bool)v[7]) SoftRight(scene, 390);
                    Grade(scene, 400, (double)v[4], (double)v[5], (double)v[6]);
                    FooterBand(scene, 522, 0.62);
                    using (Bitmap bg = Frame(frame, scene))
                    using (Bitmap pv = Preview(bg)) {
                        bg.Save(Path.Combine(outDir, "background-" + v[0] + ".png"), ImageFormat.Png);
                        pv.Save(Path.Combine(outDir, "preview-" + v[0] + ".png"), ImageFormat.Png);
                    }
                }
            }
        }
    }
}
'@
[LauncherBg]::Run((Resolve-Path $Art).Path, $FramePath, $Out)
Get-ChildItem $Out -Filter *.png | Select-Object Name, Length
