/** Kopfzeile: Instrument, Marktzustand, Modus, Datenquelle (Spec 22). */

import type { Coverage, Health, Instrument, MarketStatus } from '../api/types';
import { de } from '../i18n/de';

interface Props {
  health: Health | null;
  instrument: Instrument | null;
  /** Marktzustand aus dem Handelskalender. Frueher stand hier die Session der
   *  zuletzt ANALYSIERTEN Bar - bei altem Datenbestand also dauerhaft
   *  "geschlossen", waehrend nebenan Kurse hereinliefen. */
  market: MarketStatus | null;
  coverage: Coverage[];
  symbols: string[];
  /** Welche Symbole gespeicherte Historie haben. */
  withData: Set<string>;
  /** Name des Feeds einer laufenden Sitzung, sonst leer. */
  liveFeed: string;
  selected: string;
  onSelect: (symbol: string) => void;
  busy: boolean;
}

export function StatusBar({
  health,
  instrument,
  market,
  coverage,
  symbols,
  withData,
  liveFeed,
  selected,
  onSelect,
  busy,
}: Props) {
  // Solange der Marktzustand noch nicht da ist, wird nichts behauptet - weder
  // offen noch geschlossen. Eine Anzeige, die im Zweifel "geschlossen" sagt,
  // ist keine Auskunft, sondern eine Vermutung mit Autoritaet.
  const session = market?.session ?? '';
  const marketOpen = market?.is_open ?? false;
  const barCount = coverage
    .filter((c) => c.symbol === selected)
    .reduce((total, c) => Math.max(total, c.bar_count), 0);

  // Ein Demo-Symbol muss auf den ersten Blick als solches erkennbar sein.
  // Synthetische Daten sehen im Chart genauso aus wie echte - der einzige
  // Schutz davor, Schluesse daraus zu ziehen, ist diese Kennzeichnung.
  const isDemo = selected.endsWith('_DEMO');

  return (
    <header className={`statusbar${isDemo ? ' statusbar--demo' : ''}`}>
      <div className="statusbar__brand">
        <span className="statusbar__logo">TRADAYRI</span>
        <span className="statusbar__subtitle">{de.app.subtitle}</span>
      </div>

      <div className="statusbar__items">
        <label className="field">
          <span className="field__label">{de.status.symbol}</span>
          <select
            className="field__input"
            value={selected}
            disabled={busy || symbols.length === 0}
            onChange={(event) => onSelect(event.target.value)}
          >
            {/* Leerer Eintrag als Ausgangszustand: der Start waehlt nichts
                mehr von selbst, also muss die Auswahl auch zeigen koennen,
                dass noch nichts gewaehlt ist. */}
            {!selected && <option value="">{de.status.chooseSymbol}</option>}
            {symbols.map((symbol) => (
              <option key={symbol} value={symbol}>
                {/* Ohne gespeicherte Historie sind das die Instrumente, deren
                    Bars live hereinkommen (MNQ, NQ). Sie gehoeren in die
                    Liste, aber man muss den Unterschied sehen, bevor man
                    waehlt - nicht erst am leeren Chart danach. */}
                {symbol}
                {withData.has(symbol) ? '' : ` ${de.status.liveOnly}`}
              </option>
            ))}
          </select>
        </label>

        <Item label={de.status.market}>
          {market ? (
            <span className={marketOpen ? 'pill pill--ok' : 'pill pill--off'}>
              {marketOpen ? de.status.open : de.status.closed}
            </span>
          ) : (
            <span className="pill pill--info">-</span>
          )}
        </Item>

        <Item label={de.status.session}>
          {session ? (de.status.sessions[session] ?? session) : '-'}
        </Item>

        <Item label={de.status.mode}>
          <span className="pill pill--info">
            {health ? (de.status.modes[health.mode] ?? health.mode) : '-'}
          </span>
        </Item>

        {/* Laeuft eine Sitzung, ist DEREN Feed die Datenquelle - nicht die
            Liste der registrierten Provider. Die aendert sich nie und stand
            deshalb auch waehrend eines NT8-Betriebs auf "replay": eine Anzeige,
            die im Echtbetrieb die Wiedergabe meldet, ist schlimmer als keine. */}
        <Item label={de.status.dataFeed}>
          {liveFeed ? (
            <span className="pill pill--ok">{liveFeed}</span>
          ) : (
            health?.providers.map((p) => p.name).join(', ') || '-'
          )}
        </Item>

        <Item label={de.status.bars}>{barCount ? barCount.toLocaleString('de-DE') : '-'}</Item>

        {/* Datenfrische. Ohne sie ist ein stillstehender Chart nicht von einem
            ruhigen Markt zu unterscheiden - genau die Frage, an der Laurin am
            31.08.2026 haengenblieb ("wieso zeigt der Chart keine Livedaten?").
            Das Alter wird gezeigt, nicht bewertet: die Zahl selbst sagt, ob
            der Strom laeuft. */}
        <Item label={de.status.lastBar}>
          <DatenAlter market={market} />
        </Item>

        {instrument && (
          <Item label="Tick">
            {instrument.tick_size} = {instrument.tick_value.toFixed(2)} {instrument.currency}
          </Item>
        )}
      </div>

      {isDemo && (
        <div className="statusbar__demo-banner">
          SYNTHETISCHE DEMODATEN &ndash; keine Marktdaten. Nur zum Pruefen der Oberflaeche und
          der Detektoren geeignet, nicht fuer Aussagen ueber die Strategie.
        </div>
      )}
    </header>
  );
}

/** Wie alt die juengste gespeicherte Kerze ist.
 *
 *  Drei Zustaende, und der mittlere ist der wichtige:
 *
 *  * frisch      - Kerzen kommen an
 *  * veraltet    - der letzte Stand ist alt. **Das ist keine Stoerung**,
 *                  solange die Boerse zu ist; bei offener Boerse schon.
 *  * keine Daten - fuer dieses Instrument liegt nichts vor
 */
function DatenAlter({ market }: { market: MarketStatus | null }) {
  if (!market || market.datenalter_sekunden == null) {
    return <span className="pill pill--info">-</span>;
  }
  const alter = market.datenalter_sekunden;
  const frisch = market.daten_frisch === true;
  // Bei geschlossener Boerse ist ein alter Bestand normal und wird nicht
  // angemahnt. Eine Warnung, die immer nachts leuchtet, wird ignoriert.
  const stoerung = !frisch && market.is_open;
  return (
    <span
      className={frisch ? 'pill pill--ok' : stoerung ? 'pill pill--warn' : 'pill pill--off'}
      title={
        stoerung
          ? 'Die Boerse ist offen, aber es kommen keine Kerzen an. Laeuft ' +
            '"python -m ntbridge", und ist in NinjaTrader ein Chart mit dem ' +
            'ClaudeBridge-Indikator offen?'
          : 'Alter der juengsten gespeicherten Kerze'
      }
    >
      {formatiereAlter(alter)}
    </span>
  );
}

function formatiereAlter(sekunden: number): string {
  if (sekunden < 90) return `vor ${Math.max(0, Math.round(sekunden))} s`;
  const minuten = Math.round(sekunden / 60);
  if (minuten < 90) return `vor ${minuten} min`;
  const stunden = Math.round(minuten / 60);
  if (stunden < 48) return `vor ${stunden} h`;
  return `vor ${Math.round(stunden / 24)} Tagen`;
}

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="statusbar__item">
      <span className="statusbar__item-label">{label}</span>
      <span className="statusbar__item-value">{children}</span>
    </div>
  );
}
