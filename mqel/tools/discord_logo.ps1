# Discord application picture (Rich Presence art asset "logo", 512x512):
# the game logo cut out of the launcher art, "Rebirth" under it in the
# website's title font (Cinzel Black, gold gradient like the website's h1),
# on a soft blurred sky from the same art.
#   powershell -ExecutionPolicy Bypass -File tools\discord_logo.ps1 -Art launcher-mockups\source-art.jpg -Font <Cinzel 900 .ttf> [-Size 1024]
# Output launcher-mockups\logo.png (512) or logo-<Size>.png.
param(
    [Parameter(Mandatory = $true)][string]$Art,
    [Parameter(Mandatory = $true)][string]$Font,
    [string]$Out = '',
    [int]$Size = 512
)
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Out) { $Out = Join-Path $Here ('..\launcher-mockups\' + $(if ($Size -eq 512) { 'logo.png' } else { "logo-$Size.png" })) }
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using System.Runtime.InteropServices;

public static class DiscordLogo {
    static int Lum(byte[] a, int i) { return (a[i + 2] * 299 + a[i + 1] * 587 + a[i] * 114) / 1000; }

    // logo cut out of the art: flood fill of the bright sky from the crop
    // border; the logo's black outline stops it
    static Bitmap Cutout(Bitmap art, Rectangle r) {
        Bitmap c = art.Clone(r, PixelFormat.Format32bppArgb);
        BitmapData d = c.LockBits(new Rectangle(0, 0, c.Width, c.Height), ImageLockMode.ReadWrite, PixelFormat.Format32bppArgb);
        byte[] a = new byte[d.Stride * c.Height];
        Marshal.Copy(d.Scan0, a, 0, a.Length);
        int w = c.Width, h = c.Height;
        bool[] bg = new bool[w * h];
        Queue<int> q = new Queue<int>();
        for (int x = 0; x < w; x++) { q.Enqueue(x); q.Enqueue((h - 1) * w + x); }
        for (int y = 0; y < h; y++) { q.Enqueue(y * w); q.Enqueue(y * w + w - 1); }
        while (q.Count > 0) {
            int p = q.Dequeue();
            if (bg[p]) continue;
            int x = p % w, y = p / w;
            int j = y * d.Stride + x * 4;
            int mx = Math.Max(a[j], Math.Max(a[j + 1], a[j + 2])), mn = Math.Min(a[j], Math.Min(a[j + 1], a[j + 2]));
            // sky: bright and colored (blue/gold); white letters and the black
            // outline are not, so they stop the fill
            if (Lum(a, j) < 75 || mx - mn < 45) continue;
            bg[p] = true;
            if (x > 0) q.Enqueue(p - 1);
            if (x < w - 1) q.Enqueue(p + 1);
            if (y > 0) q.Enqueue(p - w);
            if (y < h - 1) q.Enqueue(p + w);
        }
        // pass 2: pale clouds joined to the sky, unless within 6 px of black
        // ink (the white letters are outlined in black, clouds aren't)
        bool[] ink = new bool[w * h];
        for (int y = 0; y < h; y++) for (int x = 0; x < w; x++) {
            if (Lum(a, y * d.Stride + x * 4) >= 60) continue;
            for (int dy = -6; dy <= 6; dy++) for (int dx = -6; dx <= 6; dx++) {
                int xx = x + dx, yy = y + dy;
                if (xx >= 0 && yy >= 0 && xx < w && yy < h) ink[yy * w + xx] = true;
            }
        }
        for (int p = 0; p < w * h; p++) if (bg[p]) q.Enqueue(p);
        bool[] seen = (bool[])bg.Clone();
        while (q.Count > 0) {
            int p = q.Dequeue();
            int x = p % w, y = p / w;
            int[] nb = { x > 0 ? p - 1 : -1, x < w - 1 ? p + 1 : -1, y > 0 ? p - w : -1, y < h - 1 ? p + w : -1 };
            foreach (int n in nb) {
                if (n < 0 || seen[n]) continue;
                seen[n] = true;
                int k = (n / w) * d.Stride + (n % w) * 4;
                // near the ink only warm (cream cloud) pixels go: the letters are
                // neutral white or bluish (B >= R), the cloud rim is R > B
                bool warm = a[k + 2] - a[k] >= 12;
                if (Lum(a, k) < 110 || (ink[n] && !warm)) continue;
                bg[n] = true;
                q.Enqueue(n);
            }
        }
        // peel the pale cloud rim off the lower half: light pixels touching the
        // sky go, 4 rounds; the black outline stops it
        for (int round = 0; round < 4; round++) {
            List<int> peel = new List<int>();
            for (int y = h * 2 / 5; y < h; y++) for (int x = 1; x < w - 1; x++) {
                int p = y * w + x;
                if (bg[p] || Lum(a, y * d.Stride + x * 4) < 140) continue;
                if (bg[p - 1] || bg[p + 1] || bg[p - w] || (y < h - 1 && bg[p + w])) peel.Add(p);
            }
            foreach (int p in peel) bg[p] = true;
        }
        // keep only the biggest piece (drops the detached "TM" and specks)
        int[] comp = new int[w * h];
        int best = 0, bestSize = 0, id = 0;
        for (int s0 = 0; s0 < w * h; s0++) {
            if (bg[s0] || comp[s0] != 0) continue;
            id++;
            int size = 0;
            q.Enqueue(s0); comp[s0] = id;
            while (q.Count > 0) {
                int p = q.Dequeue(); size++;
                int x = p % w, y = p / w;
                for (int dy = -1; dy <= 1; dy++) for (int dx = -1; dx <= 1; dx++) {
                    int xx = x + dx, yy = y + dy;
                    if (xx < 0 || yy < 0 || xx >= w || yy >= h) continue;
                    int n = yy * w + xx;
                    if (!bg[n] && comp[n] == 0) { comp[n] = id; q.Enqueue(n); }
                }
            }
            if (size > bestSize) { bestSize = size; best = id; }
        }
        for (int p = 0; p < w * h; p++) if (!bg[p] && comp[p] != best) bg[p] = true;
        for (int y = 0; y < h; y++) for (int x = 0; x < w; x++) {
            int p = y * w + x, i = y * d.Stride + x * 4;
            if (!bg[p]) continue;
            // soft edge: sky pixels next to the logo keep their darkness as alpha
            bool near = false;
            for (int dy = -2; dy <= 2 && !near; dy++) for (int dx = -2; dx <= 2 && !near; dx++) {
                int xx = x + dx, yy = y + dy;
                if (xx >= 0 && yy >= 0 && xx < w && yy < h && !bg[yy * w + xx]) near = true;
            }
            int al = near ? Math.Max(0, Math.Min(255, (200 - Lum(a, i)) * 255 / 125)) : 0;
            a[i] = a[i + 1] = a[i + 2] = 8;
            a[i + 3] = (byte)al;
        }
        Marshal.Copy(a, 0, d.Scan0, a.Length);
        c.UnlockBits(d);
        // tight crop to the visible logo, so centering is exact
        int x0 = w, y0 = h, x1 = 0, y1 = 0;
        for (int y = 0; y < h; y++) for (int x = 0; x < w; x++)
            if (a[y * d.Stride + x * 4 + 3] > 40) { x0 = Math.Min(x0, x); x1 = Math.Max(x1, x); y0 = Math.Min(y0, y); y1 = Math.Max(y1, y); }
        Bitmap t = c.Clone(Rectangle.FromLTRB(x0, y0, x1 + 1, y1 + 1), PixelFormat.Format32bppArgb);
        c.Dispose();
        return t;
    }

    // bounding box of the dark logo outline in the middle of the art
    static Rectangle Find(Bitmap art) {
        int x0 = art.Width, y0 = art.Height, x1 = 0, y1 = 0;
        int cx0 = art.Width * 38 / 100, cx1 = art.Width * 60 / 100;
        for (int y = 0; y < art.Height * 75 / 100; y += 2) for (int x = cx0; x < cx1; x += 2) {
            Color c = art.GetPixel(x, y);
            if (c.R + c.G + c.B < 90) { x0 = Math.Min(x0, x); x1 = Math.Max(x1, x); y0 = Math.Min(y0, y); y1 = Math.Max(y1, y); }
        }
        return Rectangle.FromLTRB(Math.Max(0, x0 - 12), Math.Max(0, y0 - 12), Math.Min(art.Width, x1 + 14), Math.Min(art.Height, y1 + 14));
    }

    public static void Run(string artPath, string fontPath, string outPath, int S) {
        float f = S / 512f;
        using (Bitmap art = new Bitmap(artPath)) {
            Rectangle r = Find(art);
            using (Bitmap logo = Cutout(art, r))
            using (Bitmap o = new Bitmap(S, S, PixelFormat.Format32bppArgb))
            using (Graphics g = Graphics.FromImage(o)) {
                g.InterpolationMode = InterpolationMode.HighQualityBicubic;
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.PixelOffsetMode = PixelOffsetMode.HighQuality;
                // background: the art around the logo, very soft (downscale + upscale)
                int side = r.Height + 200;
                Rectangle bgSrc = new Rectangle(r.X + r.Width / 2 - side / 2, Math.Max(0, r.Y - 60), side, side);
                using (Bitmap small = new Bitmap(16, 16)) {
                    using (Graphics gs = Graphics.FromImage(small)) {
                        gs.InterpolationMode = InterpolationMode.HighQualityBilinear;
                        gs.DrawImage(art, new Rectangle(0, 0, 16, 16), bgSrc, GraphicsUnit.Pixel);
                    }
                    g.DrawImage(small, new Rectangle(-40, -40, S + 80, S + 80));
                }
                // logo: centered, big; its bottom tip goes behind "Rebirth"
                double k = Math.Min(S * 0.95 / logo.Height, S * 0.9 / logo.Width);
                int lw = (int)(logo.Width * k), lh = (int)(logo.Height * k);
                g.DrawImage(logo, new Rectangle((S - lw) / 2, (int)(S * 0.015), lw, lh));
                // "Rebirth": Cinzel Black, gold gradient, dark outline
                PrivateFontCollection pfc = new PrivateFontCollection();
                pfc.AddFontFile(fontPath);
                FontFamily fam = pfc.Families[0];
                StringFormat sf = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
                float em = 92f * f;
                GraphicsPath path = new GraphicsPath();
                RectangleF box = new RectangleF(0, 404 * f, S, 104 * f);
                path.AddString("Rebirth", fam, (int)FontStyle.Regular, em, box, sf);
                RectangleF tb = path.GetBounds();
                if (tb.Width > S - 30 * f) {   // fit the width
                    path.Reset(); em *= (S - 30 * f) / tb.Width;
                    path.AddString("Rebirth", fam, (int)FontStyle.Regular, em, box, sf);
                    tb = path.GetBounds();
                }
                using (Pen shadow = new Pen(Color.FromArgb(150, 0, 0, 0), 14 * f) { LineJoin = LineJoin.Round })
                using (Matrix m = new Matrix()) {
                    m.Translate(0, 4 * f);
                    GraphicsPath sp = (GraphicsPath)path.Clone(); sp.Transform(m);
                    g.DrawPath(shadow, sp);
                }
                using (Pen outline = new Pen(Color.FromArgb(255, 18, 13, 31), 8 * f) { LineJoin = LineJoin.Round })
                    g.DrawPath(outline, path);
                using (LinearGradientBrush gold = new LinearGradientBrush(new PointF(0, tb.Top), new PointF(0, tb.Bottom),
                                                                          Color.FromArgb(255, 255, 222, 128), Color.FromArgb(255, 185, 120, 28))) {
                    ColorBlend cb = new ColorBlend(3);
                    cb.Colors = new Color[] { Color.FromArgb(255, 255, 226, 140), Color.FromArgb(255, 242, 182, 50), Color.FromArgb(255, 185, 120, 28) };
                    cb.Positions = new float[] { 0f, 0.6f, 1f };
                    gold.InterpolationColors = cb;
                    g.FillPath(gold, path);
                }
                o.Save(outPath, ImageFormat.Png);
            }
        }
    }
}
'@
[DiscordLogo]::Run((Resolve-Path $Art).Path, (Resolve-Path $Font).Path, [System.IO.Path]::GetFullPath($Out), $Size)
Get-Item $Out | Select-Object Name, Length
