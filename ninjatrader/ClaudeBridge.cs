// =============================================================================
//  ClaudeBridge.cs  --  NinjaTrader 8 Indikator
// =============================================================================
//
//  ZWECK
//  -----
//  Schickt abgeschlossene Kerzen (OHLCV) per HTTP an einen lokal laufenden
//  Empfaenger (Python, Port 8787). Von dort aus uebernimmt das bestehende
//  Analyse-Projekt.
//
//  DIES IST EIN INDIKATOR, KEINE STRATEGY.
//  Ein Indikator kann in NinjaTrader keine Orders platzieren. Das ist Absicht
//  und kein Versehen: es gibt in diesem Projekt noch keine ausgewertete
//  Erwartungswert-Statistik, und Lucid stellt ausdruecklich klar, dass der
//  Trader die volle Verantwortung fuer Softwarefehler traegt. Automatische
//  Ausfuehrung vor der Auswertung waere eine Wette auf eine ungetestete
//  Hypothese mit dem Challenge-Konto als Einsatz.
//
//  WAS DER INDIKATOR NICHT TUT
//  ---------------------------
//  - Er zeichnet nichts in den Chart.
//  - Er platziert keine Orders und liest keine Kontodaten.
//  - Er blockiert die Chartberechnung nicht. Laeuft der Empfaenger nicht,
//    schreibt er eine Zeile in den NinjaScript-Output und macht weiter.
//
//  EINBAU: siehe README-Abschnitt "NinjaTrader einrichten".
//
//  Version 1.0.1
// =============================================================================

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class ClaudeBridge : Indicator
    {
        // ---------------------------------------------------------------------
        //  EIN einziger HttpClient fuer den gesamten Prozess
        // ---------------------------------------------------------------------
        //  "static readonly" bedeutet: es gibt genau eine Instanz, geteilt von
        //  ALLEN Chart-Instanzen dieses Indikators.
        //
        //  Warum das wichtig ist: Wuerde man je Aufruf einen neuen HttpClient
        //  anlegen, blieben die zugehoerigen TCP-Verbindungen nach dem Dispose
        //  noch Minuten im Zustand TIME_WAIT haengen. Bei einer Kerze pro Minute
        //  ueber fuenf Timeframes waeren die verfuegbaren Ports nach einigen
        //  Stunden erschoepft und gar nichts ginge mehr. Das ist ein bekannter
        //  und haeufiger Fehler.
        //
        //  Das Timeout steht hier bewusst grosszuegig: HttpClient.Timeout laesst
        //  sich nach dem ersten Request nicht mehr aendern. Das eigentliche,
        //  vom Nutzer einstellbare Timeout wird weiter unten je Anfrage ueber
        //  ein CancellationToken gesetzt.
        // ---------------------------------------------------------------------
        private static readonly HttpClient SharedClient = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(30)
        };

        private const string BridgeVersion = "1.0.1";

        // Puffer fuer historische Kerzen je Datenserie. Sie werden gesammelt und
        // in EINEM Paket verschickt, sobald NinjaTrader von der historischen
        // Berechnung auf Echtzeit umschaltet.
        private List<string>[] historicalBuffers;

        // Wie viele historische Kerzen je Datenserie hoechstens gesammelt
        // werden - abhaengig vom Timeframe, siehe HistoricalBarsFor.
        private int[] historicalLimits;

        // Kerzen, deren Versand fehlgeschlagen ist. Sie werden beim naechsten
        // erfolgreichen Versand mitgeschickt, damit ein kurzer Aussetzer des
        // Empfaengers keine dauerhafte Luecke in den Daten hinterlaesst.
        private readonly List<string> retryBuffer = new List<string>();
        private readonly object retryLock = new object();

        // Zeitzone, in der NinjaTrader die Bar-Zeitstempel liefert.
        private TimeZoneInfo sourceTimeZone;

        // Zusaetzliche Timeframes, aus dem Parameter geparst (in Minuten).
        private List<int> additionalMinutes;

        // ---------------------------------------------------------------------
        //  Lebenszyklus
        // ---------------------------------------------------------------------
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Sendet abgeschlossene Kerzen an den lokalen Claude-Chart-Bot. "
                            + "Zeichnet nichts und handelt nicht.";
                Name = "ClaudeBridge";

                // OnBarClose: der Indikator rechnet einmal pro abgeschlossener
                // Kerze. Das ist der Normalfall und erzeugt genau einen HTTP-
                // Aufruf je Kerze und Timeframe.
                Calculate = Calculate.OnBarClose;

                // Der Indikator soll nichts im Chart darstellen.
                IsOverlay = false;
                DisplayInDataBox = false;
                DrawOnPricePanel = false;
                PaintPriceMarkers = false;

                // Weiterrechnen, auch wenn der Chart-Tab nicht im Vordergrund
                // ist. Ohne das wuerde die Datenlieferung pausieren, sobald du
                // auf einen anderen Tab wechselst.
                // HINWEIS: Sollte der NinjaScript-Compiler diese eine Zeile
                // bemaengeln, kannst du sie ersatzlos loeschen - alles andere
                // funktioniert weiterhin.
                IsSuspendedWhileInactive = false;

                // --- Einstellbare Parameter, Vorbelegung ---
                ReceiverUrl = "http://127.0.0.1:8787/bars";
                RequestTimeoutMs = 1500;

                // Basiswert fuer die 1-Minuten-Ebene. Groebere Timeframes
                // bekommen automatisch weniger (siehe HistoricalBarsFor).
                //
                // Warum 3000 und nicht 500: eine Globex-Session dauert 23
                // Stunden, also 1380 Minutenkerzen. Fuer Vortageshoch, -tief
                // und -schluss braucht es die VORSESSION KOMPLETT plus die
                // laufende - mindestens 2760 Kerzen. Mit 500 (8,3 Stunden)
                // waeren PDH/PDL/PDC ab dem ersten Lauf nicht berechenbar,
                // und zwar ohne jede Fehlermeldung.
                HistoricalBarsBase = 3000;
                MinimumHistoricalBars = 250;

                AdditionalMinuteTimeframes = "5,15";
                IncludeDailySeries = false;
                TimeZoneIdOverride = "";
                MaxRetryBuffer = 200;
                VerboseLogging = false;
            }
            else if (State == State.Configure)
            {
                // -------------------------------------------------------------
                //  Zusaetzliche Datenserien anmelden
                // -------------------------------------------------------------
                //  Damit liefert EINE Indikator-Instanz auf einem 1-Minuten-
                //  Chart gleich mehrere Timeframes. Du brauchst also nicht fuenf
                //  Charts nebeneinander, sondern nur eines je Instrument.
                //
                //  Wichtig: AddDataSeries darf ausschliesslich hier in
                //  State.Configure aufgerufen werden.
                //
                //  BESCHRAENKUNG, die du beim Einrichten kennen musst:
                //  Sekundaerserien erben den geladenen Zeitraum des Charts
                //  ("Days to load"). Ein 1-Minuten-Chart mit 5 Tagen liefert
                //  einer Tagesserie also nur 5 Tageskerzen. Deshalb gehoeren
                //  Tages- und Stundenebene auf ein eigenes Chart mit grossem
                //  Ladezeitraum - siehe Einbau-Anleitung.
                // -------------------------------------------------------------
                additionalMinutes = ParseTimeframeList(AdditionalMinuteTimeframes);

                foreach (int minutes in additionalMinutes)
                    AddDataSeries(BarsPeriodType.Minute, minutes);

                // Tagesebene bewusst ueber BarsPeriodType.Day, NICHT ueber
                // 1440 Minuten:
                //
                //   BarsPeriodType.Day  folgt der Trading-Hours-Vorlage des
                //                       Kontrakts, also der Globex-Session
                //                       18:00-17:00 ET.
                //   Minute mit 1440     zaehlt schlicht 1440 Minuten Uhrzeit
                //                       ab einem beliebigen Anker.
                //
                // Die beiden liegen um Stunden auseinander. Da PDH/PDL/PDC
                // genau aus dieser Session-Abgrenzung entstehen, waere die
                // Minutenvariante lautlos falsch.
                if (IncludeDailySeries)
                    AddDataSeries(BarsPeriodType.Day, 1);
            }
            else if (State == State.DataLoaded)
            {
                // Zeitzone bestimmen, in der die Bar-Zeitstempel stehen.
                sourceTimeZone = ResolveTimeZone();

                // Je Datenserie einen eigenen Puffer fuer die Historie plus die
                // Anzahl Kerzen, die fuer diesen Timeframe sinnvoll ist.
                historicalBuffers = new List<string>[BarsArray.Length];
                historicalLimits = new int[BarsArray.Length];

                for (int i = 0; i < BarsArray.Length; i++)
                {
                    historicalBuffers[i] = new List<string>();
                    historicalLimits[i] = HistoricalBarsFor(TimeframeMinutes(BarsArray[i].BarsPeriod));
                }

                Log(string.Format(
                    "ClaudeBridge {0} bereit. Instrument {1}, {2} Datenserie(n), Zeitzone {3}, Ziel {4}",
                    BridgeVersion,
                    Instrument.MasterInstrument.Name,
                    BarsArray.Length,
                    sourceTimeZone.Id,
                    ReceiverUrl), true);

                for (int i = 0; i < BarsArray.Length; i++)
                {
                    string label = TimeframeLabel(BarsArray[i].BarsPeriod);
                    Log(string.Format(
                        "  Serie {0}: {1} - Ziel {2} historische Kerzen",
                        i, label ?? "NICHT UNTERSTUETZT", historicalLimits[i]), true);
                }
            }
            else if (State == State.Realtime)
            {
                // Umschaltung von historischer Berechnung auf Echtzeit.
                // Jetzt die gesammelte Historie in einem Paket schicken.
                FlushHistoricalBuffers();
            }
            else if (State == State.Terminated)
            {
                // Der geteilte HttpClient wird bewusst NICHT freigegeben - er
                // gehoert dem Prozess, nicht dieser Chart-Instanz. Andere
                // Instanzen benutzen ihn moeglicherweise noch.
                Log("ClaudeBridge beendet.", true);
            }
        }

        // ---------------------------------------------------------------------
        //  Wird bei jeder abgeschlossenen Kerze aufgerufen
        // ---------------------------------------------------------------------
        protected override void OnBarUpdate()
        {
            // BarsInProgress sagt, WELCHE Datenserie gerade dran ist:
            // 0 = der Chart selbst, 1..n = die per AddDataSeries hinzugefuegten.
            int series = BarsInProgress;

            // Erste Kerze einer Serie ueberspringen - dort fehlen Vorgaengerwerte.
            if (CurrentBars[series] < 1)
                return;

            // Bei OnEachTick nur beim ersten Tick der neuen Kerze senden, sonst
            // wuerde jede einzelne Preisbewegung einen HTTP-Aufruf ausloesen.
            if (Calculate != Calculate.OnBarClose && !IsFirstTickOfBar)
                return;

            BarsPeriod period = BarsArray[series].BarsPeriod;
            string timeframe = TimeframeLabel(period);
            if (timeframe == null)
            {
                // Einmal melden statt bei jeder Kerze.
                if (CurrentBars[series] == 1)
                {
                    if (period.BarsPeriodType == BarsPeriodType.Minute && period.Value == 1440)
                        Log(
                            "Datenserie mit 1440 Minuten wird uebersprungen. 1440-Minuten-Bars "
                            + "folgen NICHT der Session-Definition des Kontrakts und liegen "
                            + "gegenueber dem CME-Handelstag um Stunden versetzt - daraus "
                            + "berechnete Vortagesmarken waeren falsch. Bitte stattdessen ein "
                            + "Tages-Chart verwenden oder 'Tagesserie mitliefern' einschalten.",
                            true);
                    else
                        Log(string.Format(
                            "Datenserie {0} hat einen nicht unterstuetzten Chart-Typ ({1}) "
                            + "und wird uebersprungen. Bitte Minuten- oder Tageskerzen verwenden.",
                            series, period.BarsPeriodType), true);
                }
                return;
            }

            string json = BuildBarJson(series, timeframe);

            if (State == State.Historical)
            {
                // Historie sammeln statt einzeln verschicken. Sonst gaebe es
                // beim Chartstart hunderte HTTP-Aufrufe in Folge.
                List<string> buffer = historicalBuffers[series];
                buffer.Add(json);
                if (buffer.Count > historicalLimits[series])
                    buffer.RemoveAt(0);   // nur die juengsten N behalten
                return;
            }

            // Echtzeit: sofort senden, ohne auf die Antwort zu warten.
            SendAsync(new List<string> { json }, "realtime");
        }

        // ---------------------------------------------------------------------
        //  Historie in einem Paket verschicken
        // ---------------------------------------------------------------------
        private void FlushHistoricalBuffers()
        {
            if (historicalBuffers == null)
                return;

            for (int series = 0; series < historicalBuffers.Length; series++)
            {
                List<string> buffer = historicalBuffers[series];
                if (buffer == null || buffer.Count == 0)
                    continue;

                string label = TimeframeLabel(BarsArray[series].BarsPeriod) ?? "?";
                int wanted = historicalLimits[series];

                Log(string.Format("Sende {0} historische Kerzen fuer {1} (angefordert {2}).",
                    buffer.Count, label, wanted), true);

                // NinjaTrader kann nur liefern, was der Chart geladen hat.
                // Kommt weniger an als angefordert, ist fast immer der
                // Ladezeitraum des Charts zu klein - das muss sichtbar sein,
                // sonst fehlen spaeter stillschweigend die Vortagesmarken.
                if (buffer.Count < wanted)
                    Log(string.Format(
                        "  WARNUNG: nur {0} von {1} Kerzen fuer {2} vorhanden. "
                        + "Erhoehe den Ladezeitraum des Charts "
                        + "(Rechtsklick > Datenserie > 'Days to load'). "
                        + "Fuer Vortageshoch/-tief werden zwei volle Sessions gebraucht.",
                        buffer.Count, wanted, label), true);

                SendAsync(new List<string>(buffer), "historisch");
                buffer.Clear();
            }
        }

        // ---------------------------------------------------------------------
        //  JSON fuer eine einzelne Kerze bauen
        // ---------------------------------------------------------------------
        private string BuildBarJson(int series, string timeframe)
        {
            Bars bars = BarsArray[series];

            // Time[0] ist der SCHLUSSzeitpunkt der Kerze, in der Anzeigezeitzone
            // von NinjaTrader. Wir schicken beides mit - die umgerechnete
            // UTC-Zeit und die Originalzeit samt Zeitzonen-ID. Der Empfaenger
            // kann damit pruefen, ob die Umrechnung plausibel ist, statt still
            // um Stunden verschobene Daten zu speichern.
            DateTime localTime = Times[series][0];
            DateTime utcTime;
            try
            {
                utcTime = TimeZoneInfo.ConvertTimeToUtc(
                    DateTime.SpecifyKind(localTime, DateTimeKind.Unspecified),
                    sourceTimeZone);
            }
            catch (Exception)
            {
                // Kann bei der Sommerzeit-Umstellung passieren, wenn eine
                // Ortszeit doppelt oder gar nicht existiert. Dann lieber die
                // Rohzeit als UTC markieren und den Empfaenger meckern lassen,
                // als die Kerze wegzuwerfen.
                utcTime = DateTime.SpecifyKind(localTime, DateTimeKind.Utc);
            }

            StringBuilder json = new StringBuilder(384);
            json.Append("{");
            Append(json, "instrument", bars.Instrument.MasterInstrument.Name);
            json.Append(",");
            Append(json, "ntInstrument", bars.Instrument.FullName);
            json.Append(",");
            Append(json, "timeframe", timeframe);
            json.Append(",");
            Append(json, "timestampUtc", utcTime.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture));
            json.Append(",");
            Append(json, "timestampLocal", localTime.ToString("yyyy-MM-ddTHH:mm:ss", CultureInfo.InvariantCulture));
            json.Append(",");
            Append(json, "timeZoneId", sourceTimeZone.Id);
            json.Append(",");
            AppendNumber(json, "open", Opens[series][0]);
            json.Append(",");
            AppendNumber(json, "high", Highs[series][0]);
            json.Append(",");
            AppendNumber(json, "low", Lows[series][0]);
            json.Append(",");
            AppendNumber(json, "close", Closes[series][0]);
            json.Append(",");
            AppendNumber(json, "volume", Volumes[series][0]);

            // -----------------------------------------------------------------
            //  Bid-/Ask-Volumen (kumulatives Delta)
            // -----------------------------------------------------------------
            //  Standard-NinjaTrader liefert KEIN Bid-/Ask-Volumen je Kerze.
            //  Dafuer braucht es das kostenpflichtige Add-on "Order Flow +"
            //  und volumetrische Bars.
            //
            //  Wir senden hier bewusst null statt einer Schaetzung aus Auf- und
            //  Abwaertskerzen: eine Schaetzung saehe aus wie eine Messung und
            //  waere keine. Der Empfaenger weist das Feld entsprechend als
            //  "nicht verfuegbar" mit Begruendung aus.
            //
            //  NACHRUESTEN MIT ORDER FLOW +:
            //  Hier die volumetrischen Werte auslesen und statt "null" einsetzen.
            //  Das ist die einzige Stelle, die dafuer geaendert werden muss.
            // -----------------------------------------------------------------
            json.Append(",\"bidVolume\":null,\"askVolume\":null");

            json.Append(",");
            Append(json, "source", "ninjatrader");
            json.Append(",");
            Append(json, "bridgeVersion", BridgeVersion);
            json.Append("}");

            return json.ToString();
        }

        // ---------------------------------------------------------------------
        //  Versand - grundsaetzlich ohne Warten auf die Antwort
        // ---------------------------------------------------------------------
        //  DER WICHTIGSTE TEIL DIESER DATEI.
        //
        //  NinjaScript-Methoden laufen auf dem Berechnungs-Thread der Plattform.
        //  Wuerde man hier auf das Ergebnis des HTTP-Aufrufs warten (etwa mit
        //  .Result oder .Wait()), stuende die Chartberechnung so lange still -
        //  bei einem nicht erreichbaren Empfaenger bis zum Timeout. Genau
        //  dieser Fehler ist im NinjaTrader-Forum als Ursache eingefrorener
        //  Oberflaechen dokumentiert.
        //
        //  Deshalb: Task.Run startet den Versand im Hintergrund, die Methode
        //  kehrt sofort zurueck, und JEDE Ausnahme wird innen abgefangen.
        //  Eine Ausnahme, die aus einem Hintergrund-Task entkommt, koennte
        //  NinjaTrader beenden.
        // ---------------------------------------------------------------------
        private void SendAsync(List<string> barsJson, string kind)
        {
            // Werte in lokale Variablen kopieren: der Hintergrund-Task darf
            // nicht auf Indikator-Zustand zugreifen, der sich inzwischen
            // geaendert haben koennte.
            string url = ReceiverUrl;
            int timeoutMs = RequestTimeoutMs;
            bool verbose = VerboseLogging;
            int retryCapacity = MaxRetryBuffer;

            // Haengengebliebene Kerzen aus frueheren Fehlversuchen mitschicken.
            List<string> payloadItems;
            lock (retryLock)
            {
                payloadItems = new List<string>(retryBuffer.Count + barsJson.Count);
                payloadItems.AddRange(retryBuffer);
                payloadItems.AddRange(barsJson);
                retryBuffer.Clear();
            }

            string body = "{\"bars\":[" + string.Join(",", payloadItems.ToArray()) + "]}";
            int itemCount = payloadItems.Count;

            Task.Run(async () =>
            {
                try
                {
                    using (CancellationTokenSource cancellation =
                           new CancellationTokenSource(TimeSpan.FromMilliseconds(timeoutMs)))
                    using (StringContent content =
                           new StringContent(body, Encoding.UTF8, "application/json"))
                    {
                        HttpResponseMessage response =
                            await SharedClient.PostAsync(url, content, cancellation.Token)
                                              .ConfigureAwait(false);

                        if (!response.IsSuccessStatusCode)
                        {
                            Requeue(payloadItems, retryCapacity);
                            Log(string.Format(
                                "Empfaenger antwortete mit {0} ({1} Kerzen, {2}). "
                                + "Kerzen zwischengespeichert.",
                                (int)response.StatusCode, itemCount, kind), true);
                        }
                        else if (verbose)
                        {
                            Log(string.Format("{0} Kerze(n) gesendet ({1}).", itemCount, kind), false);
                        }
                    }
                }
                catch (TaskCanceledException)
                {
                    Requeue(payloadItems, retryCapacity);
                    Log(string.Format(
                        "Zeitueberschreitung nach {0} ms beim Senden von {1} Kerze(n). "
                        + "Laeuft der Empfaenger? Kerzen zwischengespeichert.",
                        timeoutMs, itemCount), true);
                }
                catch (Exception exception)
                {
                    Requeue(payloadItems, retryCapacity);
                    Log(string.Format(
                        "Versand fehlgeschlagen ({0}: {1}). {2} Kerze(n) zwischengespeichert.",
                        exception.GetType().Name, exception.Message, itemCount), true);
                }
            });
        }

        // Fehlgeschlagene Kerzen zurueck in den Puffer, aber begrenzt: bei einem
        // tagelang abgeschalteten Empfaenger soll der Speicher nicht volllaufen.
        private void Requeue(List<string> items, int capacity)
        {
            lock (retryLock)
            {
                retryBuffer.InsertRange(0, items);
                int excess = retryBuffer.Count - capacity;
                if (excess > 0)
                    retryBuffer.RemoveRange(0, excess);   // aelteste zuerst verwerfen
            }
        }

        // ---------------------------------------------------------------------
        //  Hilfsfunktionen
        // ---------------------------------------------------------------------

        // Ausgabe im Fenster "NinjaScript-Output" (Neu > NinjaScript-Output).
        private void Log(string message, bool always)
        {
            if (always || VerboseLogging)
                Print(string.Format("[ClaudeBridge {0:HH:mm:ss}] {1}", DateTime.Now, message));
        }

        // Zeitzone der Bar-Zeitstempel ermitteln.
        private TimeZoneInfo ResolveTimeZone()
        {
            if (!string.IsNullOrWhiteSpace(TimeZoneIdOverride))
            {
                try
                {
                    return TimeZoneInfo.FindSystemTimeZoneById(TimeZoneIdOverride.Trim());
                }
                catch (Exception)
                {
                    Log(string.Format(
                        "Zeitzone '{0}' unbekannt - verwende stattdessen die Windows-Zeitzone '{1}'. "
                        + "Gueltige Werte sind z.B. 'US Eastern Standard Time' oder 'Central Standard Time'.",
                        TimeZoneIdOverride, TimeZoneInfo.Local.Id), true);
                }
            }

            // Standardfall: NinjaTrader zeigt Zeiten in der Windows-Zeitzone an.
            // Weicht deine NinjaTrader-Einstellung davon ab (Tools > Optionen >
            // Allgemein > Zeitzone), trage sie oben unter TimeZoneIdOverride ein.
            return TimeZoneInfo.Local;
        }

        // "5,15,60" -> [5, 15, 60], ohne Duplikate.
        // 1440 wird ausdruecklich abgelehnt: dafuer gibt es den Schalter
        // "Tagesserie mitliefern", der die echte Session-Definition benutzt.
        private List<int> ParseTimeframeList(string raw)
        {
            List<int> result = new List<int>();
            if (string.IsNullOrWhiteSpace(raw))
                return result;

            foreach (string part in raw.Split(','))
            {
                int minutes;
                if (!int.TryParse(part.Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out minutes))
                    continue;
                if (minutes <= 0 || result.Contains(minutes))
                    continue;

                if (minutes == 1440)
                {
                    Log(
                        "1440 in 'Zusaetzliche Minuten-Timeframes' wird ignoriert. "
                        + "1440-Minuten-Bars folgen nicht der Session-Definition des "
                        + "Kontrakts. Bitte den Schalter 'Tagesserie mitliefern' benutzen "
                        + "oder ein eigenes Tages-Chart verwenden.", true);
                    continue;
                }

                result.Add(minutes);
            }
            return result;
        }

        // NinjaTrader-Periode -> Kuerzel, das das Python-Projekt erwartet.
        private static string TimeframeLabel(BarsPeriod period)
        {
            if (period.BarsPeriodType == BarsPeriodType.Day && period.Value == 1)
                return "1d";

            if (period.BarsPeriodType == BarsPeriodType.Minute)
            {
                // Bewusst KEIN Mapping 1440 -> "1d": diese Bars folgen nicht
                // der Handelszeiten-Vorlage des Kontrakts. Sie hier als
                // Tageskerzen auszugeben, waere genau die Art stiller Fehler,
                // die dieses Projekt vermeiden will.
                if (period.Value == 1440) return null;
                if (period.Value == 60) return "1h";
                return period.Value.ToString(CultureInfo.InvariantCulture) + "m";
            }

            return null;   // Tick-, Volumen-, Range-Charts: nicht unterstuetzt
        }

        // Laenge eines Bars in Minuten - Grundlage fuer die Skalierung der
        // Historie. Fuer Tageskerzen wird die Globex-Sessionlaenge (23 h)
        // angesetzt, nicht 24 h.
        private static int TimeframeMinutes(BarsPeriod period)
        {
            if (period.BarsPeriodType == BarsPeriodType.Day)
                return 23 * 60;
            if (period.BarsPeriodType == BarsPeriodType.Minute)
                return Math.Max(1, period.Value);
            return 1;
        }

        // Wie viele historische Kerzen fuer diesen Timeframe gesammelt werden.
        //
        //   Basis 3000 gilt fuer die 1-Minuten-Ebene (gut zwei Globex-Sessions).
        //   Groebere Timeframes decken denselben Zeitraum mit weniger Kerzen ab,
        //   brauchen aber eine Untergrenze: EMA200 und die Swing-Erkennung
        //   arbeiten sonst ins Leere.
        //
        //   1m  -> 3000   (rund 2,2 Sessions)
        //   5m  ->  600   (rund 2,2 Sessions)
        //   15m ->  250   (Untergrenze, rund 2,7 Sessions)
        //   1h  ->  250   (Untergrenze, rund 10 Sessions - EMA200 gedeckt)
        //   1d  ->  250   (Untergrenze, rund ein Handelsjahr)
        private int HistoricalBarsFor(int timeframeMinutes)
        {
            if (HistoricalBarsBase <= 0)
                return 0;

            int scaled = Math.Max(1, HistoricalBarsBase / Math.Max(1, timeframeMinutes));
            int withFloor = Math.Max(MinimumHistoricalBars, scaled);
            return Math.Min(HistoricalBarsBase, withFloor);
        }

        // --- JSON von Hand, ohne externe Bibliothek ---
        // NinjaTrader laeuft auf .NET Framework 4.8; Newtonsoft.Json ist zwar
        // vorhanden, aber die Version ist an NinjaTrader gebunden. Fuer diese
        // paar Felder ist Handarbeit robuster als eine Abhaengigkeit.

        private static void Append(StringBuilder builder, string key, string value)
        {
            builder.Append('"').Append(key).Append("\":");
            builder.Append('"').Append(Escape(value)).Append('"');
        }

        private static void AppendNumber(StringBuilder builder, string key, double value)
        {
            builder.Append('"').Append(key).Append("\":");

            // InvariantCulture ist hier NICHT optional: auf einem deutschen
            // Windows wuerde ToString() "21345,25" liefern - mit Komma. Das ist
            // kein gueltiges JSON und der Empfaenger wuerde die Kerze ablehnen.
            if (double.IsNaN(value) || double.IsInfinity(value))
                builder.Append("null");
            else
                builder.Append(value.ToString("R", CultureInfo.InvariantCulture));
        }

        private static string Escape(string value)
        {
            if (string.IsNullOrEmpty(value))
                return string.Empty;

            StringBuilder escaped = new StringBuilder(value.Length + 8);
            foreach (char character in value)
            {
                switch (character)
                {
                    case '"':  escaped.Append("\\\""); break;
                    case '\\': escaped.Append("\\\\"); break;
                    case '\n': escaped.Append("\\n");  break;
                    case '\r': escaped.Append("\\r");  break;
                    case '\t': escaped.Append("\\t");  break;
                    default:
                        if (character < ' ')
                            escaped.Append("\\u").Append(((int)character).ToString("x4", CultureInfo.InvariantCulture));
                        else
                            escaped.Append(character);
                        break;
                }
            }
            return escaped.ToString();
        }

        // ---------------------------------------------------------------------
        //  Einstellbare Parameter
        //  (erscheinen im Dialog, wenn du den Indikator an den Chart haengst)
        // ---------------------------------------------------------------------

        [NinjaScriptProperty]
        [Display(Name = "Empfaenger-URL", Order = 1, GroupName = "Verbindung",
                 Description = "Adresse des lokalen Python-Empfaengers. Normalerweise unveraendert lassen.")]
        public string ReceiverUrl { get; set; }

        [NinjaScriptProperty]
        [Range(100, 10000)]
        [Display(Name = "Timeout (ms)", Order = 2, GroupName = "Verbindung",
                 Description = "Wie lange auf den Empfaenger gewartet wird, bevor die Kerze "
                             + "zwischengespeichert und spaeter erneut gesendet wird.")]
        public int RequestTimeoutMs { get; set; }

        [NinjaScriptProperty]
        [Range(0, 20000)]
        [Display(Name = "Historische Kerzen (Basis 1-Minuten-Ebene)", Order = 3, GroupName = "Daten",
                 Description = "Wie viele 1-Minuten-Kerzen beim Laden uebertragen werden. "
                             + "Groebere Timeframes bekommen automatisch anteilig weniger. "
                             + "3000 entspricht gut zwei Globex-Sessions - erst damit sind "
                             + "Vortageshoch/-tief/-schluss ab dem ersten Lauf berechenbar. "
                             + "0 schaltet die Historie ab.")]
        public int HistoricalBarsBase { get; set; }

        [NinjaScriptProperty]
        [Range(0, 5000)]
        [Display(Name = "Untergrenze historische Kerzen", Order = 4, GroupName = "Daten",
                 Description = "So viele Kerzen bekommt jeder Timeframe mindestens, auch wenn "
                             + "die anteilige Rechnung weniger ergaebe. 250 deckt EMA200 und "
                             + "die Swing-Erkennung ab.")]
        public int MinimumHistoricalBars { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Zusaetzliche Minuten-Timeframes", Order = 5, GroupName = "Daten",
                 Description = "Kommagetrennt, z.B. '5,15'. Diese Serien liefert dieselbe "
                             + "Indikator-Instanz zusaetzlich mit. ACHTUNG: sie erben den "
                             + "Ladezeitraum des Charts. 1440 ist hier ungueltig - fuer die "
                             + "Tagesebene den Schalter darunter benutzen.")]
        public string AdditionalMinuteTimeframes { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Tagesserie mitliefern", Order = 6, GroupName = "Daten",
                 Description = "Fuegt echte Tageskerzen hinzu (BarsPeriodType.Day), die der "
                             + "Handelszeiten-Vorlage des Kontrakts folgen. Nur sinnvoll auf "
                             + "einem Chart mit grossem Ladezeitraum - auf einem 1-Minuten-Chart "
                             + "mit 5 Tagen kaemen genau 5 Tageskerzen an.")]
        public bool IncludeDailySeries { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Zeitzone (optional)", Order = 7, GroupName = "Daten",
                 Description = "Leer lassen, wenn NinjaTrader Zeiten in der Windows-Zeitzone "
                             + "anzeigt (Normalfall). Sonst die NinjaTrader-Zeitzone eintragen, "
                             + "z.B. 'US Eastern Standard Time'.")]
        public string TimeZoneIdOverride { get; set; }

        [NinjaScriptProperty]
        [Range(0, 5000)]
        [Display(Name = "Zwischenspeicher (Kerzen)", Order = 6, GroupName = "Verbindung",
                 Description = "Wie viele nicht zugestellte Kerzen hoechstens aufgehoben werden, "
                             + "solange der Empfaenger nicht erreichbar ist.")]
        public int MaxRetryBuffer { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Ausfuehrliches Log", Order = 7, GroupName = "Diagnose",
                 Description = "Schreibt jede gesendete Kerze in den NinjaScript-Output. "
                             + "Nur zum Einrichten einschalten.")]
        public bool VerboseLogging { get; set; }
    }
}
