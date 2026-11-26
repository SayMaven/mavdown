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
                // Gatefold pure monochrome / neutral scheme (OKLCH contrast-enforced untuk dark & light)
                double bgL = isDark ? Math.Clamp(0.145 + dom.L * 0.045, 0.140, 0.190) : Math.Clamp(0.955 + (dom.L - 0.9) * 0.06, 0.935, 0.975);
                double bgC = isDark ? 0.008 : 0.004;
                double bgHue = 250.0;
                var bgCol = LchToColor(bgL, bgC, bgHue);

                double surfL = bgL + sign * 0.038;
                double surf2L = bgL + sign * 0.070;
                var surfCol = LchToColor(surfL, bgC * 1.05, bgHue);
                var surf2Col = LchToColor(surf2L, bgC * 1.15, bgHue);

                var mTextEnf = EnforceContrast(isDark ? 0.95 : 0.18, 0.004, bgHue, bgCol, 10.5, sign);
                var mText2Enf = EnforceContrast(isDark ? 0.82 : 0.36, 0.005, bgHue, bgCol, 6.2, sign);
                var mText3Enf = EnforceContrast(isDark ? 0.65 : 0.50, 0.006, bgHue, bgCol, 4.2, sign);

                var mAccEnf = EnforceContrast(isDark ? 0.78 : 0.46, 0.014, bgHue, bgCol, 4.0, sign);
                var mAccInkEnf = EnforceContrast(isDark ? 0.86 : 0.38, 0.012, bgHue, bgCol, 5.2, sign);
                var mAcc2Enf = EnforceContrast(isDark ? 0.74 : 0.52, 0.022, 265.0, bgCol, 3.2, sign);
                var glowCol = LchToColor(isDark ? 0.50 : 0.60, 0.020, bgHue);

                var monoResult = new PaletteResult
                {
                    IsDark = isDark,
                    Background = new PaletteColor(bgL, bgC, bgHue, bgCol),
                    Surface = new PaletteColor(surfL, bgC * 1.05, bgHue, surfCol),
                    Surface2 = new PaletteColor(surf2L, bgC * 1.15, bgHue, surf2Col),
                    Accent = new PaletteColor(mAccEnf.L, mAccEnf.C, mAccEnf.h, mAccEnf.rgb),
                    AccentInk = new PaletteColor(mAccInkEnf.L, mAccInkEnf.C, mAccInkEnf.h, mAccInkEnf.rgb),
                    Accent2 = new PaletteColor(mAcc2Enf.L, mAcc2Enf.C, mAcc2Enf.h, mAcc2Enf.rgb),
                    Glow = new PaletteColor(isDark ? 0.50 : 0.60, 0.020, bgHue, glowCol),
                    Text = new PaletteColor(mTextEnf.L, mTextEnf.C, mTextEnf.h, mTextEnf.rgb),
                    Text2 = new PaletteColor(mText2Enf.L, mText2Enf.C, mText2Enf.h, mText2Enf.rgb),
                    Text3 = new PaletteColor(mText3Enf.L, mText3Enf.C, mText3Enf.h, mText3Enf.rgb)
                };

                foreach (var c in clusters.Take(8))
                {
                    monoResult.Swatches.Add(LchToColor(c.L, c.C, c.H));
                }

                return monoResult;
            }

            // Chromatic Palette (Cover Berwarna - Constant Hue Ramp tanpa Hue Drift)
            var acc = ranked[0].c;
            var acc2Src = ranked.FirstOrDefault(x => HueDist(x.c.H, acc.H) > 28);
            var acc2 = acc2Src != null ? acc2Src.c : new Cluster { L = acc.L, C = acc.C * 0.85, H = (acc.H + 38) % 360 };

            double chrBgHue = dom.C > 0.025 ? dom.H : (colorfulness > 0.02 ? massHue : acc.H);
            double bgChromaSrc = Math.Max(dom.C, colorfulness * 0.72);

            double chrBgL = isDark ? Math.Clamp(0.145 + dom.L * 0.045, 0.140, 0.190) : Math.Clamp(0.955 + (dom.L - 0.9) * 0.06, 0.935, 0.975);
            double chrBgC = isDark ? Math.Clamp(bgChromaSrc * 0.30, 0.008, 0.032) : Math.Clamp(bgChromaSrc * 0.18, 0.004, 0.022);

            var chrBgCol = LchToColor(chrBgL, chrBgC, chrBgHue);

            double chrSurfL = chrBgL + sign * 0.040;
            double chrSurf2L = chrBgL + sign * 0.072;
            var chrSurfCol = LchToColor(chrSurfL, chrBgC * 1.06, chrBgHue);
            var chrSurf2Col = LchToColor(chrSurf2L, chrBgC * 1.12, chrBgHue);

            double tC = Math.Min(0.014, chrBgC * 0.45);
            double textL = isDark ? 0.95 : 0.18;
            double text2L = isDark ? 0.83 : 0.36;
            double text3L = isDark ? 0.66 : 0.50;

            var textEnf = EnforceContrast(textL, tC, chrBgHue, chrBgCol, 10.5, sign);
            var text2Enf = EnforceContrast(text2L, tC, chrBgHue, chrBgCol, 6.2, sign);
            var text3Enf = EnforceContrast(text3L, tC, chrBgHue, chrBgCol, 4.2, sign);

            double accL = isDark ? Math.Clamp(acc.L, 0.68, 0.84) : Math.Clamp(acc.L, 0.44, 0.64);
            var accEnf = EnforceContrast(accL, Math.Clamp(acc.C * 1.05, 0.08, 0.20), acc.H, chrBgCol, isDark ? 3.8 : 3.2, sign);
            var accInkEnf = EnforceContrast(isDark ? Math.Max(accEnf.L, 0.78) : Math.Min(accEnf.L, 0.42), Math.Clamp(acc.C * 0.90, 0.06, 0.16), acc.H, chrBgCol, 4.8, sign);
            var acc2Enf = EnforceContrast(isDark ? 0.76 : 0.50, Math.Clamp(acc2.C, 0.06, 0.17), acc2.H, chrBgCol, 3.2, sign);

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
            const double baseH = 262.0;
            const double accH = 264.0;
            var bgCol = LchToColor(0.145, 0.016, baseH);
            var surfCol = LchToColor(0.185, 0.019, baseH);
            var surf2Col = LchToColor(0.217, 0.022, baseH);
            var accCol = LchToColor(0.680, 0.165, accH);
            var accInkCol = LchToColor(0.830, 0.095, accH);
            var acc2Col = LchToColor(0.760, 0.110, 215.0);
            var glowCol = LchToColor(0.540, 0.140, accH);
            var textCol = LchToColor(0.955, 0.008, baseH);
            var text2Col = LchToColor(0.840, 0.012, baseH);
            var text3Col = LchToColor(0.670, 0.014, baseH);

            return new PaletteResult
            {
                IsDark = true,
                Background = new PaletteColor(0.145, 0.016, baseH, bgCol),
                Surface = new PaletteColor(0.185, 0.019, baseH, surfCol),
                Surface2 = new PaletteColor(0.217, 0.022, baseH, surf2Col),
                Accent = new PaletteColor(0.680, 0.165, accH, accCol),
                AccentInk = new PaletteColor(0.830, 0.095, accH, accInkCol),
                Accent2 = new PaletteColor(0.760, 0.110, 215.0, acc2Col),
                Glow = new PaletteColor(0.540, 0.140, accH, glowCol),
                Text = new PaletteColor(0.955, 0.008, baseH, textCol),
                Text2 = new PaletteColor(0.840, 0.012, baseH, text2Col),
                Text3 = new PaletteColor(0.670, 0.014, baseH, text3Col),
                Swatches = new List<Color>
                {
                    surfCol, surf2Col, acc2Col, accCol,
                    LchToColor(0.700, 0.145, 162.0), LchToColor(0.560, 0.125, 162.0)
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
                double sign = palette.IsDark ? 1.0 : -1.0;
                double bgL = palette.Background.L;
                double bgC = palette.Background.C;
                double bgH = palette.Background.H;
                double surfL = palette.Surface.L;
                double surfC = palette.Surface.C;
                double surf2L = palette.Surface2.L;
                double surf2C = palette.Surface2.C;
                double accL = palette.Accent.L;
                double accC = palette.Accent.C;
                double accH = palette.Accent.H;

                Color bgMaster = palette.Background.Color;
                Color surfCol = palette.Surface.Color;
                Color surf2Col = palette.Surface2.Color;
                Color accentCol = palette.Accent.Color;
                Color glowCol = palette.Glow.Color;
                Color titleTextCol = palette.Text.Color;
                Color bodyTextCol = palette.Text2.Color;
                Color mutedTextCol = palette.Text3.Color;

                // Turunan warna murni di ruang OKLCH (tanpa sRGB scaling / hue drift)
                Color dimTextCol = LchToColor(palette.Text3.L - sign * 0.09, palette.Text3.C, palette.Text3.H);
                Color sidebarBg = LchToColor(bgL + sign * 0.014, bgC * 0.92, bgH);

                Color cardBgEnd = LchToColor(surfL - sign * 0.014, surfC * 0.95, bgH);
                Color cardBorderStart = LchToColor(bgL + sign * 0.13, Math.Min(accC * 0.35, 0.055), bgH, 145);
                Color cardBorderEnd = LchToColor(bgL + sign * 0.06, Math.Min(accC * 0.20, 0.035), bgH, 55);

                Color innerBgEnd = LchToColor(surf2L - sign * 0.012, surf2C * 0.95, bgH);
                Color innerBorder = LchToColor(bgL + sign * 0.10, Math.Min(accC * 0.25, 0.040), bgH, 115);

                Color segmentBg = LchToColor(bgL - sign * 0.015, bgC * 0.85, bgH);
                Color controlHoverCol = LchToColor(surf2L + sign * 0.035, Math.Min(surf2C + 0.010, 0.050), bgH);
                Color controlHoverBorderCol = LchToColor(surf2L + sign * 0.12, Math.Min(accC * 0.45, 0.070), accH, 175);
                Color controlPressedCol = LchToColor(surfL, surfC, bgH);

                Color borderDark = LchToColor(bgL + sign * 0.085, bgC * 1.1, bgH, 110);
                Color borderLight = LchToColor(bgL + sign * 0.145, Math.Min(accC * 0.30, 0.050), bgH, 130);

                Color navActiveStart = LchToColor(bgL + sign * 0.065, Math.Min(accC * 0.42, 0.075), accH, 215);
                Color navActiveEnd = LchToColor(bgL + sign * 0.035, Math.Min(accC * 0.22, 0.045), accH, 140);
                Color navActiveBorderCol = LchToColor(accL, accC * 0.75, accH, 140);
                Color navActiveFg = palette.AccentInk.Color;

                // Kontras teks di atas Accent berdasarkan OKLCH L (boundary L > 0.6)
                Color accentFg = accL > 0.62 ? LchToColor(0.14, 0.01, bgH) : Colors.White;
                Color accentHoverCol = LchToColor(accL + sign * 0.06, Math.Min(accC * 1.04, 0.24), accH);
                Color segActiveEnd = LchToColor(accL - 0.065, accC * 0.95, accH);

                // Brush instances (Vertical Single Direction: Top-to-Bottom 0,0 -> 0,1)
                var bgMasterBrush = new SolidColorBrush(bgMaster);
                var sidebarBgBrush = new SolidColorBrush(sidebarBg);
                var cardBgBrush = new LinearGradientBrush(surfCol, cardBgEnd, new Point(0, 0), new Point(0, 1));
                var cardBorderBrush = new LinearGradientBrush(cardBorderStart, cardBorderEnd, new Point(0, 0), new Point(0, 1));
                var innerBrush = new LinearGradientBrush(surf2Col, innerBgEnd, new Point(0, 0), new Point(0, 1));
                var innerBorderBrush = new SolidColorBrush(innerBorder);
                var segmentBgBrush = new SolidColorBrush(segmentBg);
                var controlHoverBrush = new SolidColorBrush(controlHoverCol);
                var controlHoverBorderBrush = new SolidColorBrush(controlHoverBorderCol);
                var controlPressedBrush = new SolidColorBrush(controlPressedCol);
                var accentBrush = new SolidColorBrush(accentCol);
                var accentHoverBrush = new SolidColorBrush(accentHoverCol);
                var accentFgBrush = new SolidColorBrush(accentFg);
                var titleTextBrush = new SolidColorBrush(titleTextCol);
                var bodyTextBrush = new SolidColorBrush(bodyTextCol);
                var mutedTextBrush = new SolidColorBrush(mutedTextCol);
                var dimTextBrush = new SolidColorBrush(dimTextCol);
                var navActiveBgBrush = new LinearGradientBrush(navActiveStart, navActiveEnd, new Point(0, 0), new Point(1, 0));
                var navActiveBorderBrush = new SolidColorBrush(navActiveBorderCol);
                var navActiveFgBrush = new SolidColorBrush(navActiveFg);
                var segActiveBrush = new LinearGradientBrush(accentCol, segActiveEnd, new Point(0, 0), new Point(0, 1));

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
                Application.Current.Resources["BrushControlHover"] = controlHoverBrush;
                Application.Current.Resources["BrushControlHoverBorder"] = controlHoverBorderBrush;
                Application.Current.Resources["BrushControlPressed"] = controlPressedBrush;
                Application.Current.Resources["BrushAccentIndigo"] = accentBrush;
                Application.Current.Resources["BrushAccentIndigoHover"] = accentHoverBrush;
                Application.Current.Resources["BrushAccentForeground"] = accentFgBrush;
                Application.Current.Resources["BrushTextTitle"] = titleTextBrush;
                Application.Current.Resources["BrushTextBody"] = bodyTextBrush;
                Application.Current.Resources["BrushTextMuted"] = mutedTextBrush;
                Application.Current.Resources["BrushTextDim"] = dimTextBrush;
                Application.Current.Resources["BrushNavActiveBg"] = navActiveBgBrush;
                Application.Current.Resources["BrushNavActiveBorder"] = navActiveBorderBrush;
                Application.Current.Resources["BrushNavActiveFg"] = navActiveFgBrush;
                Application.Current.Resources["BrushGradientSegmentActive"] = segActiveBrush;

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
