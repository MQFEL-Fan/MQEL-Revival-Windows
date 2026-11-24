<#
Discord server icon: the castle with the red dragon from the launcher art,
cropped square, with a word ("Reborn" by default) in gold Cinzel at the
bottom, kept inside the circle Discord cuts out (server list: rounded
square / circle at 48 px). Writes <Out>\server-icon-<word>.png (512x512)
and <Out>\server-icon-<word>-preview.png (how it looks in the server list:
circle and rounded square, 48 px and 96 px, on Discord's dark grey).

  powershell -ExecutionPolicy Bypass -File tools\discord_server_icon.ps1 `
      -Art launcher-mockups\source-art.jpg -Font _temp60\fonts\cinzel-900.ttf -Word Reborn
#>
param(
    [Parameter(Mandatory)] [string]$Art,
    [Parameter(Mandatory)] [string]$Font,
    [string]$Word = "Reborn",
    [string]$Out = "",
    # crop of the art (1920x1080 launcher picture): left, top, size
    [int]$X = 138, [int]$Y = 96, [int]$S = 590
)
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Out) { $Out = Join-Path (Split-Path -Parent $Here) "launcher-mockups" }
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @"
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;

public static class ServerIcon {
    const int N = 512;

    static GraphicsPath RoundRect(float x, float y, float w, float h, float r) {
        GraphicsPath p = new GraphicsPath();
        p.AddArc(x, y, 2 * r, 2 * r, 180, 90);
        p.AddArc(x + w - 2 * r, y, 2 * r, 2 * r, 270, 90);
        p.AddArc(x + w - 2 * r, y + h - 2 * r, 2 * r, 2 * r, 0, 90);
        p.AddArc(x, y + h - 2 * r, 2 * r, 2 * r, 90, 90);
        p.CloseFigure();
        return p;
    }

    public static Bitmap Make(string art, string font, string word, int cx, int cy, int cs) {
        Bitmap src = new Bitmap(art);
        Bitmap bmp = new Bitmap(N, N, PixelFormat.Format32bppArgb);
        using (Graphics g = Graphics.FromImage(bmp)) {
            g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.PixelOffsetMode = PixelOffsetMode.HighQuality;
            g.DrawImage(src, new Rectangle(0, 0, N, N), new Rectangle(cx, cy, cs, cs), GraphicsUnit.Pixel);
            // dark band at the bottom so the word reads at 48 px
            using (LinearGradientBrush shade = new LinearGradientBrush(new Point(0, 270), new Point(0, N),
                       Color.FromArgb(0, 10, 8, 24), Color.FromArgb(235, 10, 8, 24)))
                g.FillRectangle(shade, 0, 270, N, N - 270);

            PrivateFontCollection pfc = new PrivateFontCollection();
            pfc.AddFontFile(font);
            FontFamily fam = pfc.Families[0];
            string text = word.ToUpperInvariant();
            // largest size whose width fits the circle's chord at the text line
            float size = 160, maxW = 400;
            GraphicsPath path = null;
            RectangleF tb = RectangleF.Empty;
            for (; size > 20; size -= 2) {
                path = new GraphicsPath();
                path.AddString(text, fam, (int)FontStyle.Bold, size, new PointF(0, 0), StringFormat.GenericTypographic);
                tb = path.GetBounds();
                if (tb.Width <= maxW && tb.Height <= 92) break;
            }
            // centre: horizontally, text block between y 352 and 444
            float top = 352 + (92 - tb.Height) / 2;
            using (Matrix m = new Matrix()) {
                m.Translate(N / 2f - tb.Left - tb.Width / 2, top - tb.Top);
                path.Transform(m);
            }
            tb = path.GetBounds();
            using (Pen shadow = new Pen(Color.FromArgb(170, 0, 0, 0), 22) { LineJoin = LineJoin.Round }) {
                GraphicsPath sp = (GraphicsPath)path.Clone();
                using (Matrix m = new Matrix()) { m.Translate(0, 6); sp.Transform(m); }
                g.DrawPath(shadow, sp);
            }
            using (Pen outline = new Pen(Color.FromArgb(255, 18, 13, 31), 12) { LineJoin = LineJoin.Round })
                g.DrawPath(outline, path);
            using (LinearGradientBrush gold = new LinearGradientBrush(new PointF(0, tb.Top), new PointF(0, tb.Bottom),
                       Color.White, Color.White)) {
                ColorBlend cb = new ColorBlend();
                cb.Colors = new Color[] { Color.FromArgb(255, 255, 236, 160), Color.FromArgb(255, 245, 190, 60),
                                          Color.FromArgb(255, 190, 120, 26) };
                cb.Positions = new float[] { 0f, 0.5f, 1f };
                gold.InterpolationColors = cb;
                g.FillPath(gold, path);
            }
        }
        src.Dispose();
        return bmp;
    }

    public static Bitmap Preview(Bitmap icon) {
        Bitmap p = new Bitmap(360, 140, PixelFormat.Format32bppArgb);
        using (Graphics g = Graphics.FromImage(p)) {
            g.Clear(Color.FromArgb(255, 30, 31, 34));
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            int[] sizes = { 48, 96 };
            int x = 16;
            foreach (int s in sizes) {
                for (int shape = 0; shape < 2; shape++) {
                    int y = (140 - s) / 2;
                    GraphicsPath clip = shape == 0 ? new GraphicsPath() : RoundRect(x, y, s, s, s * 0.3f);
                    if (shape == 0) clip.AddEllipse(x, y, s, s);
                    g.SetClip(clip);
                    g.DrawImage(icon, new Rectangle(x, y, s, s));
                    g.ResetClip();
                    x += s + 16;
                }
            }
        }
        return p;
    }
}
"@
$icon = [ServerIcon]::Make((Resolve-Path $Art).Path, (Resolve-Path $Font).Path, $Word, $X, $Y, $S)
$name = "server-icon-" + $Word.ToLowerInvariant()
$file = Join-Path $Out "$name.png"
$icon.Save($file, [System.Drawing.Imaging.ImageFormat]::Png)
$prev = [ServerIcon]::Preview($icon)
$prev.Save((Join-Path $Out "$name-preview.png"), [System.Drawing.Imaging.ImageFormat]::Png)
$icon.Dispose(); $prev.Dispose()
"{0} ({1:N0} bytes)" -f $file, (Get-Item $file).Length
