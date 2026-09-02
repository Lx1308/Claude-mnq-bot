import { useState } from 'react';
import { de } from '../i18n/de';


export function OrderPanel() {
  
  const [size, setSize] = useState(1);
  const [price, setPrice] = useState('');
  const [sl, setSl] = useState(20);
  const [tp, setTp] = useState(40);
  const [trailing, setTrailing] = useState(0);
  const [reason, setReason] = useState('');
  const [orderType, setOrderType] = useState('MARKET');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const submitOrder = async (side: 'LONG' | 'SHORT') => {
    setBusy(true);
    setError(null);
    setSuccess(false);
    try {
      const response = await fetch('/api/order/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: 'MNQ',
          side,
          qty: size,
          price: Number(price) || 0,
          stop_price: orderType === 'STOP' ? Number(price) || 0 : undefined,
          // ABSTAENDE in Punkten, nicht Kurse. Bis zum 02.09.2026 gingen
          // diese Werte als `stop_loss`/`take_profit` raus - Felder, die
          // absolute Kurse meinen. NinjaTrader legte daraus ein
          // Verkaufslimit bei Kurs 40 an, das sofort ausfuehrbar war und die
          // Position eine Sekunde nach dem Einstieg wieder schloss.
          stop_loss_points: sl,
          take_profit_points: tp,
          kind: orderType,
        }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Order fehlgeschlagen');
      }
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel__header">
        <h2 className="panel__title">{de.order.title}</h2>
      </div>
      <div className="panel__content">
        <div className="form-group-row">
          <div className="form-group">
            <label>Order Typ</label>
            <select value={orderType} onChange={e => setOrderType(e.target.value)} className="form-input">
              <option value="MARKET">{de.order.market}</option>
              <option value="STOP">Stop</option>
              <option value="LIMIT">Limit</option>
            </select>
          </div>
          <div className="form-group">
            <label>Preis (nur Stop/Limit)</label>
            <input type="number" value={price} onChange={e => setPrice(e.target.value)} className="form-input" disabled={orderType === 'MARKET'} />
          </div>
        </div>

        <div className="form-group-row">
          <div className="form-group">
            <label>{de.order.size}</label>
            <input type="number" min="1" value={size} onChange={e => setSize(Number(e.target.value))} className="form-input" />
          </div>
          <div className="form-group">
            <label>{de.order.sl}</label>
            <input type="number" min="0" value={sl} onChange={e => setSl(Number(e.target.value))} className="form-input" />
          </div>
        </div>

        <div className="form-group-row">
          <div className="form-group">
            <label>{de.order.tp}</label>
            <input type="number" min="0" value={tp} onChange={e => setTp(Number(e.target.value))} className="form-input" />
          </div>
          <div className="form-group">
            <label>{de.order.trailing}</label>
            <input type="number" min="0" value={trailing} onChange={e => setTrailing(Number(e.target.value))} className="form-input" />
          </div>
        </div>

        <div className="form-group">
          <label>{de.order.reason}</label>
          <input type="text" value={reason} onChange={e => setReason(e.target.value)} className="form-input" placeholder="Idee / Setups..." />
        </div>

        {error && <div className="text-error" style={{marginBottom: 10}}>{error}</div>}
        {success && <div className="text-success" style={{marginBottom: 10}}>Order gesendet!</div>}

        <div className="order-actions">
          <button 
            type="button" 
            className="btn btn--buy" 
            disabled={busy}
            onClick={() => submitOrder('LONG')}
          >
            {de.order.submitBuy}
          </button>
          <button 
            type="button" 
            className="btn btn--sell" 
            disabled={busy}
            onClick={() => submitOrder('SHORT')}
          >
            {de.order.submitSell}
          </button>
        </div>
      </div>
    </div>
  );
}


