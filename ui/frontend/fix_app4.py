import re
with open('src/App.tsx', 'r') as f:
    text = f.read()

# Replace loadData
old_load = """      try {
        const [h, i, o, c, s, st, integ, logs] = await Promise.all([
          api.health(),
          api.instruments(),
          api.overlays(symbol, timeframe),
          api.coverage(),
          api.session(),
          api.strategy(),
          api.integrity(),
          api.logs(200),
        ]);
        setHealth(h);
        setInstruments(i);
        setOverlays(o);
        setCoverage(c);
        setSnapshot(s);
        setStrategy(st);
        setIntegrity(integ);
        setLogEntries(logs);
      }"""
new_load = """      try {
        const [h, i, o, c, s, st, integ, logs, tradesData] = await Promise.all([
          api.health(),
          api.instruments(),
          api.overlays(symbol, timeframe),
          api.coverage(),
          api.session(),
          api.strategy(),
          api.integrity(),
          api.logs(200),
          api.trades(symbol).catch(() => [])
        ]);
        setHealth(h);
        setInstruments(i);
        setOverlays(o);
        setTrades(tradesData);
        setCoverage(c);
        setSnapshot(s);
        setStrategy(st);
        setIntegrity(integ);
        setLogEntries(logs);
      }"""
text = text.replace(old_load, new_load)
with open('src/App.tsx', 'w') as f:
    f.write(text)
