with open('src/App.tsx', 'r') as f:
    text = f.read()

import re
text = re.sub(r'const \[h, i, o, c, s, st, integ, logs\] = await Promise\.all\(\[[\s\S]*?\]\);',
'''const [h, i, o, c, s, st, integ, logs, tradesData] = await Promise.all([
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
        setTrades(tradesData);''', text)

with open('src/App.tsx', 'w') as f:
    f.write(text)
