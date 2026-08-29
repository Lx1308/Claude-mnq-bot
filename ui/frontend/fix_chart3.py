with open('src/chart/TradeChart.tsx', 'r') as f:
    text = f.read()

text = text.replace("props.trades", "trades")
text = text.replace("export function TradeChart({", "export function TradeChart({\n  trades,")

with open('src/chart/TradeChart.tsx', 'w') as f:
    f.write(text)
