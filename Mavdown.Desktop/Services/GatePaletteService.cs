using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Media.Imaging;

namespace Mavdown.Desktop.Services
{
    public class PaletteColor
    {
        public double L { get; set; }
        public double C { get; set; }
        public double H { get; set; }
        public Color Color { get; set; }
        public string Hex { get; set; } = "#000000";

        public PaletteColor(double l, double c, double h, Color col)
        {
            L = l;
            C = c;
            H = h;
            Color = col;
            Hex = $"#{col.R:X2}{col.G:X2}{col.B:X2}";
        }
    }

    public class PaletteResult
    {
        public bool IsDark { get; set; } = true;
        public PaletteColor Background { get; set; } = null!;
        public PaletteColor Surface { get; set; } = null!;
        public PaletteColor Surface2 { get; set; } = null!;
        public PaletteColor Accent { get; set; } = null!;
        public PaletteColor AccentInk { get; set; } = null!;
        public PaletteColor Accent2 { get; set; } = null!;
        public PaletteColor Glow { get; set; } = null!;
        public PaletteColor Text { get; set; } = null!;
        public PaletteColor Text2 { get; set; } = null!;
        public PaletteColor Text3 { get; set; } = null!;
        public List<Color> Swatches { get; set; } = new List<Color>();
    }

    /// <summary>
    /// Pure C# Port of Gatefold foobar2000 palette-core.js (OKLab/OKLCH color science & k-means clustering).
    /// Extracts cover colors and dynamically skins Mavdown Desktop UI like Gatefold theme.
    /// </summary>
    public static class GatePaletteService
    {
        public static string CurrentThemeMode = "dark"; // "dark" (dark-adaptive), "auto" (full gatefold adaptive), "static"

        #region Colour Science (OKLab / OKLCH / sRGB)
        private static double SrgbToLinear(double c) =>
            c <= 0.04045 ? c / 12.92 : Math.Pow((c + 0.055) / 1.055, 2.4);

        private static double LinearToSrgb(double c) =>
            c <= 0.0031308 ? 12.92 * c : 1.055 * Math.Pow(Math.Max(0, c), 1.0 / 2.4) - 0.055;

        private static double[] LinearRgbToOklab(double r, double g, double b)
        {
            double l = Math.Cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
            double m = Math.Cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
            double s = Math.Cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
            return new double[]
            {
                0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
                1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
                0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s
            };
        }

        private static double[] OklabToLinearRgb(double L, double a, double b)
        {
            double l = Math.Pow(L + 0.3963377774 * a + 0.2158037573 * b, 3);
            double m = Math.Pow(L - 0.1055613458 * a - 0.0638541728 * b, 3);
            double s = Math.Pow(L - 0.0894841775 * a - 1.291485548 * b, 3);
            return new double[]
            {
                4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
                -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
                -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s
            };
        }

        private static double Hypot(double x, double y) => Math.Sqrt(x * x + y * y);

        private static (double L, double C, double h) ToLch(double L, double a, double b)
        {
            double c = Hypot(a, b);
            double h = (Math.Atan2(b, a) * 180.0) / Math.PI;
            if (h < 0) h += 360.0;
            return (L, c, h);
        }

        public static Color LchToColor(double L, double C, double h, byte alpha = 255)
        {
            L = Math.Clamp(L, 0.0, 1.0);
            double[] lin = OklabToLinearRgb(L, C * Math.Cos(h * Math.PI / 180.0), C * Math.Sin(h * Math.PI / 180.0));
            if (!(lin[0] >= -1e-4 && lin[0] <= 1.0001 && lin[1] >= -1e-4 && lin[1] <= 1.0001 && lin[2] >= -1e-4 && lin[2] <= 1.0001))
            {
                double lo = 0.0, hi = C;
                for (int i = 0; i < 22; i++)
                {
                    double mid = (lo + hi) / 2.0;
                    lin = OklabToLinearRgb(L, mid * Math.Cos(h * Math.PI / 180.0), mid * Math.Sin(h * Math.PI / 180.0));
                    if (lin[0] >= -1e-4 && lin[0] <= 1.0001 && lin[1] >= -1e-4 && lin[1] <= 1.0001 && lin[2] >= -1e-4 && lin[2] <= 1.0001) lo = mid; else hi = mid;
                }
                lin = OklabToLinearRgb(L, lo * Math.Cos(h * Math.PI / 180.0), lo * Math.Sin(h * Math.PI / 180.0));
            }

            byte r = (byte)Math.Clamp(Math.Round(LinearToSrgb(lin[0]) * 255.0), 0, 255);
            byte g = (byte)Math.Clamp(Math.Round(LinearToSrgb(lin[1]) * 255.0), 0, 255);
            byte bVal = (byte)Math.Clamp(Math.Round(LinearToSrgb(lin[2]) * 255.0), 0, 255);
            return Color.FromArgb(alpha, r, g, bVal);
        }

        private static double RelLuminance(Color col)
        {
            double r = SrgbToLinear(col.R / 255.0);
            double g = SrgbToLinear(col.G / 255.0);
            double b = SrgbToLinear(col.B / 255.0);
            return 0.2126 * r + 0.7152 * g + 0.0722 * b;
        }

        private static double Contrast(Color colA, Color colB)
        {
            double a = RelLuminance(colA), b = RelLuminance(colB);
            return (Math.Max(a, b) + 0.05) / (Math.Min(a, b) + 0.05);
        }

        private static (double L, double C, double h, Color rgb) EnforceContrast(double L, double C, double h, Color bgRgb, double target, double dir)
        {
            for (int i = 0; i < 60; i++)
            {
                Color rgb = LchToColor(L, C, h);
                if (Contrast(rgb, bgRgb) >= target) return (L, C, h, rgb);
                L = Math.Clamp(L + dir * 0.012, 0.0, 1.0);
                if (L <= 0 || L >= 1.0) break;
            }
            return (L, C, h, LchToColor(L, C, h));
        }

        private static double HueDist(double a, double b)
        {
            double d = Math.Abs(a - b) % 360.0;
            return d > 180.0 ? 360.0 - d : d;
        }
        #endregion

        #region K-Means Clustering
        private class Cluster
        {
            public double[] Lab = new double[3];
            public double L, C, H;
            public double Share;
        }

        private static Func<double> CreateMulberry32(uint seed)
        {
            return () =>
            {
                seed = (seed + 0x6d2b79f5u);
                uint t = seed ^ (seed >> 15);
                t = Math.Min(uint.MaxValue, t * (1u | seed));
                t = (t + ((t ^ (t >> 7)) * (61u | t))) ^ t;
                return ((t ^ (t >> 14)) & 0xFFFFFFFFu) / 4294967296.0;
            };
        }

        private static List<Cluster> Kmeans(float[] pts, float[] wts, int n, int K, int iters)
        {
            if (n == 0) return new List<Cluster>();
            var rnd = CreateMulberry32(0x5eed);
            double LW = 0.7;

            double Dist2(int i, double[] c)
            {
                double dL = (pts[i * 3] - c[0]) * LW;
                double da = pts[i * 3 + 1] - c[1];
                double db = pts[i * 3 + 2] - c[2];
                return dL * dL + da * da + db * db;
            }

            var cents = new List<double[]>();
            int first = (int)Math.Floor(rnd() * n);
            cents.Add(new double[] { pts[first * 3], pts[first * 3 + 1], pts[first * 3 + 2] });
            double[] dmin = new double[n];
            Array.Fill(dmin, double.PositiveInfinity);

            while (cents.Count < K)
            {
                double total = 0;
                double[] c = cents[^1];
                for (int i = 0; i < n; i++)
                {
                    double d = Dist2(i, c);
                    if (d < dmin[i]) dmin[i] = d;
                    total += dmin[i] * wts[i];
                }
                if (total <= 1e-12) break;
                double r = rnd() * total;
                int pick = n - 1;
                for (int i = 0; i < n; i++)
                {
                    r -= dmin[i] * wts[i];
                    if (r <= 0) { pick = i; break; }
                }
                cents.Add(new double[] { pts[pick * 3], pts[pick * 3 + 1], pts[pick * 3 + 2] });
            }

            int k = cents.Count;
            int[] assign = new int[n];
            for (int it = 0; it < iters; it++)
            {
                double[][] sum = new double[k][];
                for (int ci = 0; ci < k; ci++) sum[ci] = new double[4];

                for (int i = 0; i < n; i++)
                {
                    double best = double.PositiveInfinity;
                    int bj = 0;
                    for (int j = 0; j < k; j++)
                    {
                        double d = Dist2(i, cents[j]);
                        if (d < best) { best = d; bj = j; }
                    }
                    assign[i] = bj;
                    float w = wts[i];
                    sum[bj][0] += pts[i * 3] * w;
                    sum[bj][1] += pts[i * 3 + 1] * w;
                    sum[bj][2] += pts[i * 3 + 2] * w;
                    sum[bj][3] += w;
                }

                for (int j = 0; j < k; j++)
                {
                    if (sum[j][3] > 0)
                    {
                        cents[j][0] = sum[j][0] / sum[j][3];
                        cents[j][1] = sum[j][1] / sum[j][3];
                        cents[j][2] = sum[j][2] / sum[j][3];
                    }
                }
            }

            double totalW = 0;
            double[] clusterW = new double[k];
            for (int i = 0; i < n; i++)
            {
                clusterW[assign[i]] += wts[i];
                totalW += wts[i];
            }

            var clusters = new List<Cluster>();
            for (int j = 0; j < k; j++)
            {
                if (clusterW[j] <= 0) continue;
                var lch = ToLch(cents[j][0], cents[j][1], cents[j][2]);
                clusters.Add(new Cluster
                {
                    Lab = new double[] { cents[j][0], cents[j][1], cents[j][2] },
                    L = lch.L,
                    C = lch.C,
                    H = lch.h,
                    Share = clusterW[j] / (totalW > 0 ? totalW : 1.0)
                });
            }

            return MergeClusters(clusters);
        }

        private static List<Cluster> MergeClusters(List<Cluster> cl)
        {
            var outList = new List<Cluster>();
            cl.Sort((a, b) => b.Share.CompareTo(a.Share));

            foreach (var c in cl)
            {
                var m = outList.FirstOrDefault(o =>
                    Hypot(o.Lab[0] - c.Lab[0], o.Lab[1] - c.Lab[1]) < 0.045 &&
                    Math.Abs(o.Lab[2] - c.Lab[2]) < 0.045);

                if (m != null)
                {
                    double t = m.Share + c.Share;
                    m.Lab[0] = (m.Lab[0] * m.Share + c.Lab[0] * c.Share) / t;
                    m.Lab[1] = (m.Lab[1] * m.Share + c.Lab[1] * c.Share) / t;
                    m.Lab[2] = (m.Lab[2] * m.Share + c.Lab[2] * c.Share) / t;
                    m.Share = t;
                    var lch = ToLch(m.Lab[0], m.Lab[1], m.Lab[2]);
                    m.L = lch.L;
                    m.C = lch.C;
                    m.H = lch.h;
                }
                else
                {
                    outList.Add(c);
                }
            }

            outList.Sort((a, b) => b.Share.CompareTo(a.Share));
            return outList;
        }
        #endregion

        #region Palette Builder
        public static PaletteResult ExtractPalette(BitmapSource bitmap, string mode = "dark")
        {
            if (bitmap == null) return GetDefaultMavdownPalette();

            int w = 64, h = 64;
            var resized = new TransformedBitmap(bitmap, new ScaleTransform((double)w / bitmap.PixelWidth, (double)h / bitmap.PixelHeight));
            var formatted = new FormatConvertedBitmap(resized, PixelFormats.Bgra32, null, 0);

            int stride = w * 4;
            byte[] pixels = new byte[h * stride];
            formatted.CopyPixels(pixels, stride, 0);

            int n = w * h;
            float[] pts = new float[n * 3];
            float[] wts = new float[n];
            int validCount = 0;
            double cx = (w - 1) / 2.0, cy = (h - 1) / 2.0;
            double rmax = Hypot(cx, cy);

            double[] lut = new double[256];
            for (int i = 0; i < 256; i++) lut[i] = SrgbToLinear(i / 255.0);

            for (int y = 0; y < h; y++)
            {
                for (int x = 0; x < w; x++)
                {
                    int i = (y * w + x) * 4;
                    byte a = pixels[i + 3];
                    if (a < 128) continue;
                    byte b = pixels[i];
                    byte g = pixels[i + 1];
                    byte r = pixels[i + 2];

                    double[] lab = LinearRgbToOklab(lut[r], lut[g], lut[b]);
                    double d = Hypot(x - cx, y - cy) / rmax;

                    pts[validCount * 3] = (float)lab[0];
                    pts[validCount * 3 + 1] = (float)lab[1];
                    pts[validCount * 3 + 2] = (float)lab[2];
                    wts[validCount] = (float)(1.15 - 0.35 * d);
                    validCount++;
                }
            }

            if (validCount == 0) return GetDefaultMavdownPalette();

            var clusters = Kmeans(pts, wts, validCount, 8, 14);
            if (clusters.Count == 0) return GetDefaultMavdownPalette();

            return BuildPalette(clusters, mode);
        }

        private static PaletteResult BuildPalette(List<Cluster> clusters, string mode)
        {
            var dom = clusters[0];
            double avgL = clusters.Sum(c => c.L * c.Share);
            double colorfulness = clusters.Sum(c => c.C * c.Share);

            double hx = 0, hy = 0;
            foreach (var c in clusters)
            {
                double w = c.Share * c.C;
                hx += Math.Cos((c.H * Math.PI) / 180.0) * w;
                hy += Math.Sin((c.H * Math.PI) / 180.0) * w;
            }
            double massHue = (Math.Atan2(hy, hx) * 180.0) / Math.PI;
            if (massHue < 0) massHue += 360.0;

            bool isDark = true;
            if (mode == "light") isDark = false;
            else if (mode == "auto") isDark = !(avgL > 0.74 && dom.L > 0.78 && dom.Share > 0.35);
            else isDark = true; // "dark" mode keeps sleek dark palette with adaptive cover hue

            double ScoreAccent(Cluster c)
            {
                if (c.C < 0.035 || c.L < 0.18 || c.L > 0.97) return -1;
                double presence = Math.Sqrt(Math.Min(c.Share, 0.35));
                double lightFit = 1 - Math.Abs(c.L - 0.64) * 0.9;
                return presence * Math.Pow(c.C, 0.9) * lightFit;
            }

            var ranked = clusters.Select(c => new { c, s = ScoreAccent(c) }).Where(x => x.s > 0).OrderByDescending(x => x.s).ToList();
            bool monochrome = ranked.Count == 0 || colorfulness < 0.022;

            double sign = isDark ? 1 : -1;

            if (monochrome)
            {
                // Gatefold pure monochrome / neutral scheme
                double bgL = isDark ? Math.Clamp(0.155 + dom.L * 0.06, 0.15, 0.215) : Math.Clamp(0.955 + (dom.L - 0.9) * 0.08, 0.93, 0.975);
                double bgC = isDark ? 0.007 : 0.004;
                double bgHue = 240.0;
                var bgCol = LchToColor(bgL, bgC, bgHue);

                double surfL = bgL + sign * 0.038;
                double surf2L = bgL + sign * 0.075;
                var surfCol = LchToColor(surfL, bgC * 1.05, bgHue);
                var surf2Col = LchToColor(surf2L, bgC * 1.15, bgHue);

                // Pure silver grey accent (Gatefold #B8BEC5)
                var accCol = LchToColor(0.78, 0.012, 240);
                var accInkCol = Color.FromRgb(0x11, 0x13, 0x17);
                var acc2Col = LchToColor(0.75, 0.022, 265); // #BCBAD7

                // Slate ambient halo glow (Gatefold #657383)
                var glowCol = LchToColor(0.48, 0.022, 240);

                var textCol = Color.FromRgb(0xF2, 0xF3, 0xF5);
                var text2Col = Color.FromRgb(0xBC, 0xBE, 0xBF);
                var text3Col = Color.FromRgb(0x88, 0x8E, 0x96);

                var monoResult = new PaletteResult
                {
                    IsDark = isDark,
                    Background = new PaletteColor(bgL, bgC, bgHue, bgCol),
                    Surface = new PaletteColor(surfL, bgC * 1.05, bgHue, surfCol),
                    Surface2 = new PaletteColor(surf2L, bgC * 1.15, bgHue, surf2Col),
                    Accent = new PaletteColor(0.78, 0.012, 240, accCol),
                    AccentInk = new PaletteColor(0.12, 0.005, 240, accInkCol),
                    Accent2 = new PaletteColor(0.75, 0.022, 265, acc2Col),
                    Glow = new PaletteColor(0.48, 0.022, 240, glowCol),
                    Text = new PaletteColor(0.97, 0.005, 240, textCol),
                    Text2 = new PaletteColor(0.80, 0.005, 240, text2Col),
                    Text3 = new PaletteColor(0.62, 0.005, 240, text3Col)
                };

                foreach (var c in clusters.Take(8))
                {
                    monoResult.Swatches.Add(LchToColor(c.L, c.C, c.H));
                }

                return monoResult;
            }

            // Chromatic Palette (Cover Berwarna)
            var acc = ranked[0].c;
            var acc2Src = ranked.FirstOrDefault(x => HueDist(x.c.H, acc.H) > 28);
            var acc2 = acc2Src != null ? acc2Src.c : new Cluster { L = acc.L, C = acc.C * 0.85, H = (acc.H + 38) % 360 };

            double chrBgHue = dom.C > 0.025 ? dom.H : (colorfulness > 0.02 ? massHue : acc.H);
            double bgChromaSrc = Math.Max(dom.C, colorfulness * 0.8);

            double chrBgL = isDark ? Math.Clamp(0.155 + dom.L * 0.06, 0.15, 0.215) : Math.Clamp(0.955 + (dom.L - 0.9) * 0.08, 0.93, 0.975);
            double chrBgC = isDark ? Math.Clamp(bgChromaSrc * 0.42, 0.008, 0.052) : Math.Clamp(bgChromaSrc * 0.22, 0.004, 0.03);

            var chrBgCol = LchToColor(chrBgL, chrBgC, chrBgHue);

            double chrSurfL = chrBgL + sign * 0.038;
            double chrSurf2L = chrBgL + sign * 0.075;
            var chrSurfCol = LchToColor(chrSurfL, chrBgC * 1.1, chrBgHue);
            var chrSurf2Col = LchToColor(chrSurf2L, chrBgC * 1.2, chrBgHue);

            double tC = Math.Min(0.018, chrBgC * 0.5);
            double textL = isDark ? 0.97 : 0.18;
            double text2L = isDark ? 0.82 : 0.38;
            double text3L = isDark ? 0.65 : 0.52;

            var textEnf = EnforceContrast(textL, tC, chrBgHue, chrBgCol, 10.0, sign);
            var text2Enf = EnforceContrast(text2L, tC, chrBgHue, chrBgCol, 6.0, sign);
            var text3Enf = EnforceContrast(text3L, tC, chrBgHue, chrBgCol, 4.0, sign);

            double accL = isDark ? Math.Clamp(acc.L, 0.70, 0.88) : Math.Clamp(acc.L, 0.48, 0.74);
            var accEnf = EnforceContrast(accL, Math.Clamp(acc.C * 1.1, 0.08, 0.22), acc.H, chrBgCol, isDark ? 3.5 : 2.4, sign);
            var accInkEnf = EnforceContrast(acc.L, acc.C, acc.H, chrBgCol, 4.6, sign);
            var acc2Enf = EnforceContrast(isDark ? 0.75 : 0.55, Math.Clamp(acc2.C, 0.06, 0.19), acc2.H, chrBgCol, 2.8, sign);

            double glowL = isDark ? 0.52 : 0.62;
            var chrGlowCol = LchToColor(glowL, Math.Clamp(acc.C, 0.05, 0.20), acc.H);

            var result = new PaletteResult
            {
                IsDark = isDark,
                Background = new PaletteColor(chrBgL, chrBgC, chrBgHue, chrBgCol),
                Surface = new PaletteColor(chrSurfL, chrBgC * 1.1, chrBgHue, chrSurfCol),
                Surface2 = new PaletteColor(chrSurf2L, chrBgC * 1.2, chrBgHue, chrSurf2Col),
                Accent = new PaletteColor(accEnf.L, accEnf.C, accEnf.h, accEnf.rgb),
                AccentInk = new PaletteColor(accInkEnf.L, accInkEnf.C, accInkEnf.h, accInkEnf.rgb),
                Accent2 = new PaletteColor(acc2Enf.L, acc2Enf.C, acc2Enf.h, acc2Enf.rgb),
                Glow = new PaletteColor(glowL, Math.Clamp(acc.C, 0.05, 0.20), acc.H, chrGlowCol),
                Text = new PaletteColor(textEnf.L, textEnf.C, textEnf.h, textEnf.rgb),
                Text2 = new PaletteColor(text2Enf.L, text2Enf.C, text2Enf.h, text2Enf.rgb),
                Text3 = new PaletteColor(text3Enf.L, text3Enf.C, text3Enf.h, text3Enf.rgb)
            };

            foreach (var c in clusters.Take(8))
            {
                result.Swatches.Add(LchToColor(c.L, c.C, c.H));
            }

            return result;
        }

        public static PaletteResult GetDefaultMavdownPalette()
        {
            return new PaletteResult
            {
                IsDark = true,
                Background = new PaletteColor(0.12, 0.02, 260, Color.FromRgb(0x08, 0x0A, 0x10)),
                Surface = new PaletteColor(0.16, 0.03, 260, Color.FromRgb(0x0E, 0x11, 0x1A)),
                Surface2 = new PaletteColor(0.20, 0.04, 260, Color.FromRgb(0x14, 0x18, 0x26)),
                Accent = new PaletteColor(0.74, 0.12, 270, Color.FromRgb(0x63, 0x66, 0xF1)),
                AccentInk = new PaletteColor(0.82, 0.09, 270, Color.FromRgb(0x93, 0xC5, 0xFD)),
                Accent2 = new PaletteColor(0.76, 0.09, 205, Color.FromRgb(0x38, 0xBD, 0xF8)),
                Glow = new PaletteColor(0.56, 0.11, 270, Color.FromRgb(0x63, 0x66, 0xF1)),
                Text = new PaletteColor(0.97, 0.01, 260, Color.FromRgb(0xF8, 0xFA, 0xFC)),
                Text2 = new PaletteColor(0.80, 0.01, 260, Color.FromRgb(0xE2, 0xE8, 0xF0)),
                Text3 = new PaletteColor(0.65, 0.01, 260, Color.FromRgb(0x94, 0xA3, 0xB8)),
                Swatches = new List<Color>
                {
                    Color.FromRgb(0x0E, 0x11, 0x1A), Color.FromRgb(0x14, 0x18, 0x26),
                    Color.FromRgb(0x38, 0xBD, 0xF8), Color.FromRgb(0x63, 0x66, 0xF1),
                    Color.FromRgb(0x10, 0xB9, 0x81), Color.FromRgb(0x05, 0x96, 0x69)
                }
            };
        }

        #region Procedural Sand / Film Grain Noise Brush Generator
        /// <summary>
        /// Generates a high-frequency, seamless 256x256 tactile sand / matte grain noise texture
        /// to eliminate gradient banding and give the dark UI an organic tactile feel.
        /// </summary>
        public static ImageBrush CreateNoiseBrush()
        {
            int size = 256;
            var wb = new WriteableBitmap(size, size, 96, 96, PixelFormats.Bgra32, null);
            byte[] pixels = new byte[size * size * 4];
            var rand = new Random(1337);

            for (int i = 0; i < pixels.Length; i += 4)
            {
                double u1 = Math.Max(1e-6, 1.0 - rand.NextDouble());
                double u2 = 1.0 - rand.NextDouble();
                double randStdNormal = Math.Sqrt(-2.0 * Math.Log(u1)) * Math.Sin(2.0 * Math.PI * u2);
                int val = (int)(128 + 24 * randStdNormal);
                byte v = (byte)Math.Clamp(val, 0, 255);

                byte a = (byte)rand.Next(3, 12);

                pixels[i] = v;     // B
                pixels[i + 1] = v; // G
                pixels[i + 2] = v; // R
                pixels[i + 3] = a; // A
            }

            wb.WritePixels(new Int32Rect(0, 0, size, size), pixels, size * 4, 0);
            wb.Freeze();

            var brush = new ImageBrush(wb)
            {
                TileMode = TileMode.Tile,
                Viewport = new Rect(0, 0, 256, 256),
                ViewportUnits = BrushMappingMode.Absolute,
                Opacity = 0.22
            };
            brush.Freeze();
            return brush;
        }
        #endregion
        #endregion

        #region UI Dynamic Theming Applier
        /// <summary>
        /// Smoothly transitions Mavdown's UI elements and brushes to match the extracted cover palette.
        /// </summary>
        public static void ApplyToWindow(MainWindow window, PaletteResult palette, bool animate = true)
        {
            if (window == null || palette == null) return;

            window.Dispatcher.Invoke(() =>
            {
                Color bgMaster = palette.Background.Color;
                Color surfCol = palette.Surface.Color;
                Color surf2Col = palette.Surface2.Color;
                Color accentCol = palette.Accent.Color;
                Color glowCol = palette.Glow.Color;
                Color titleTextCol = palette.Text.Color;
                Color bodyTextCol = palette.Text2.Color;
                Color mutedTextCol = palette.Text3.Color;

                // Hitung turunan warna harmonis
                byte rDim = (byte)(mutedTextCol.R * 0.8);
                byte gDim = (byte)(mutedTextCol.G * 0.8);
                byte bDim = (byte)(mutedTextCol.B * 0.8);
                Color dimTextCol = Color.FromRgb(rDim, gDim, bDim);

                Color sidebarBg = Color.FromArgb(255, 
                    (byte)Math.Clamp(bgMaster.R * 0.88, 0, 255), 
                    (byte)Math.Clamp(bgMaster.G * 0.88, 0, 255), 
                    (byte)Math.Clamp(bgMaster.B * 0.88, 0, 255));

                Color cardBgEnd = Color.FromArgb(255, 
                    (byte)Math.Clamp(surfCol.R * 0.78, 0, 255), 
                    (byte)Math.Clamp(surfCol.G * 0.78, 0, 255), 
                    (byte)Math.Clamp(surfCol.B * 0.78, 0, 255));

                Color cardBorderStart = Color.FromArgb(140, 
                    (byte)Math.Clamp(accentCol.R * 0.40 + surf2Col.R * 0.60, 0, 255), 
                    (byte)Math.Clamp(accentCol.G * 0.40 + surf2Col.G * 0.60, 0, 255), 
                    (byte)Math.Clamp(accentCol.B * 0.40 + surf2Col.B * 0.60, 0, 255));
                Color cardBorderEnd = Color.FromArgb(45, cardBorderStart.R, cardBorderStart.G, cardBorderStart.B);

                Color innerBgEnd = Color.FromArgb(255, 
                    (byte)Math.Clamp(surf2Col.R * 0.85, 0, 255), 
                    (byte)Math.Clamp(surf2Col.G * 0.85, 0, 255), 
                    (byte)Math.Clamp(surf2Col.B * 0.85, 0, 255));

                Color innerBorder = Color.FromArgb(110, 
                    (byte)Math.Clamp(accentCol.R * 0.30 + surf2Col.R * 0.70, 0, 255), 
                    (byte)Math.Clamp(accentCol.G * 0.30 + surf2Col.G * 0.70, 0, 255), 
                    (byte)Math.Clamp(accentCol.B * 0.30 + surf2Col.B * 0.70, 0, 255));

                Color segmentBg = Color.FromArgb(255, 
                    (byte)Math.Clamp(surfCol.R * 0.58, 0, 255), 
                    (byte)Math.Clamp(surfCol.G * 0.58, 0, 255), 
                    (byte)Math.Clamp(surfCol.B * 0.58, 0, 255));

                Color borderDark = Color.FromArgb(65, cardBorderStart.R, cardBorderStart.G, cardBorderStart.B);
                Color borderLight = Color.FromArgb(95, cardBorderStart.R, cardBorderStart.G, cardBorderStart.B);

                Color navActiveBg = Color.FromArgb(48, accentCol.R, accentCol.G, accentCol.B);
                Color navActiveFg = accentCol;

                // Tentukan kontras warna teks di atas Accent
                double accLum = (0.299 * accentCol.R + 0.587 * accentCol.G + 0.114 * accentCol.B) / 255.0;
                Color accentFg = accLum > 0.55 ? Color.FromRgb(0x11, 0x13, 0x17) : Colors.White;

                Color accentHoverCol = Color.FromArgb(255, 
                    (byte)Math.Clamp(accentCol.R * 0.88, 0, 255), 
                    (byte)Math.Clamp(accentCol.G * 0.88, 0, 255), 
                    (byte)Math.Clamp(accentCol.B * 0.88, 0, 255));

                // Brush instances (All Vertical Single Direction: Top-to-Bottom 0,0 -> 0,1)
                var bgMasterBrush = new SolidColorBrush(bgMaster);
                var sidebarBgBrush = new SolidColorBrush(sidebarBg);
                var cardBgBrush = new LinearGradientBrush(surfCol, cardBgEnd, new Point(0, 0), new Point(0, 1));
                var cardBorderBrush = new LinearGradientBrush(cardBorderStart, cardBorderEnd, new Point(0, 0), new Point(0, 1));
                var innerBrush = new LinearGradientBrush(surf2Col, innerBgEnd, new Point(0, 0), new Point(0, 1));
                var innerBorderBrush = new SolidColorBrush(innerBorder);
                var segmentBgBrush = new SolidColorBrush(segmentBg);
                var accentBrush = new SolidColorBrush(accentCol);
                var accentHoverBrush = new SolidColorBrush(accentHoverCol);
                var accentFgBrush = new SolidColorBrush(accentFg);
                var titleTextBrush = new SolidColorBrush(titleTextCol);
                var bodyTextBrush = new SolidColorBrush(bodyTextCol);
                var mutedTextBrush = new SolidColorBrush(mutedTextCol);
                var dimTextBrush = new SolidColorBrush(dimTextCol);
                var navActiveBgBrush = new SolidColorBrush(navActiveBg);
                var navActiveFgBrush = new SolidColorBrush(navActiveFg);

                // Update Application-wide Resources (semua DynamicResource langsung aktif!)
                Application.Current.Resources["BrushBgMaster"] = bgMasterBrush;
                Application.Current.Resources["BrushSidebarBg"] = sidebarBgBrush;
                Application.Current.Resources["BrushCardBg"] = cardBgBrush;
                Application.Current.Resources["BrushCardInner"] = innerBrush;
                Application.Current.Resources["BrushBorderDark"] = new SolidColorBrush(borderDark);
                Application.Current.Resources["BrushBorderLight"] = new SolidColorBrush(borderLight);
                Application.Current.Resources["BrushGatefoldCardBg"] = cardBgBrush;
                Application.Current.Resources["BrushGatefoldBorder"] = cardBorderBrush;
                Application.Current.Resources["BrushGatefoldInner"] = innerBrush;
                Application.Current.Resources["BrushGatefoldInnerBorder"] = innerBorderBrush;
                Application.Current.Resources["BrushGatefoldSegmentBg"] = segmentBgBrush;
                Application.Current.Resources["BrushAccentIndigo"] = accentBrush;
                Application.Current.Resources["BrushAccentIndigoHover"] = accentHoverBrush;
                Application.Current.Resources["BrushAccentForeground"] = accentFgBrush;
                Application.Current.Resources["BrushTextTitle"] = titleTextBrush;
                Application.Current.Resources["BrushTextBody"] = bodyTextBrush;
                Application.Current.Resources["BrushTextMuted"] = mutedTextBrush;
                Application.Current.Resources["BrushTextDim"] = dimTextBrush;
                Application.Current.Resources["BrushNavActiveBg"] = navActiveBgBrush;
                Application.Current.Resources["BrushNavActiveFg"] = navActiveFgBrush;

                // Window Background
                window.Background = bgMasterBrush;

                // 2. Named Cards Direct Binding Support
                if (window.TopCommandBar != null)
                {
                    window.TopCommandBar.Background = cardBgBrush;
                    window.TopCommandBar.BorderBrush = cardBorderBrush;
                }
                if (window.MediaInspectorCard != null)
                {
                    window.MediaInspectorCard.Background = cardBgBrush;
                    window.MediaInspectorCard.BorderBrush = cardBorderBrush;
                }
                if (window.ConfigStudioCard != null)
                {
                    window.ConfigStudioCard.Background = cardBgBrush;
                    window.ConfigStudioCard.BorderBrush = cardBorderBrush;
                }
                if (window.BottomProgressDock != null)
                {
                    window.BottomProgressDock.Background = cardBgBrush;
                    window.BottomProgressDock.BorderBrush = cardBorderBrush;
                }

                // 3. Ambient Glow around Artwork Thumbnail (Gatefold 360-degree halo)
                if (window.ArtworkGlowEffect != null)
                {
                    window.ArtworkGlowEffect.ShadowDepth = 0;
                    window.ArtworkGlowEffect.BlurRadius = 68;
                    window.ArtworkGlowEffect.Opacity = 0.85;

                    if (animate)
                    {
                        var glowAnim = new ColorAnimation(window.ArtworkGlowEffect.Color, glowCol, TimeSpan.FromMilliseconds(500));
                        window.ArtworkGlowEffect.BeginAnimation(System.Windows.Media.Effects.DropShadowEffect.ColorProperty, glowAnim);
                    }
                    else
                    {
                        window.ArtworkGlowEffect.Color = glowCol;
                    }
                }

                // 4. Equalizer Glyph Bars (.eq i)
                var eqBrush = new SolidColorBrush(accentCol);
                if (window.EqBar1 != null) window.EqBar1.Background = eqBrush;
                if (window.EqBar2 != null) window.EqBar2.Background = eqBrush;
                if (window.EqBar3 != null) window.EqBar3.Background = eqBrush;

                // 5. Hero Typography Accents
                if (window.MetaChannelText != null) window.MetaChannelText.Foreground = accentBrush;
                if (window.MetaPlatformText != null) window.MetaPlatformText.Foreground = accentBrush;
                if (window.MediaTitleText != null) window.MediaTitleText.Foreground = titleTextBrush;

                // 6. Refresh Active Tab Nav Button Highlight
                window.UpdateActiveTabHighlight();

                // 7. Update Swatches in Settings Tab
                window.UpdateCoverPaletteSwatches(palette.Swatches);
            });
        }
        #endregion
    }
}
