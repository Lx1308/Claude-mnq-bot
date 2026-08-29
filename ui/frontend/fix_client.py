with open('src/api/client.ts', 'r') as f:
    text = f.read()

text = text.replace("trades: (symbol: string) => request<any[]>(/trades?symbol=),", "trades: (symbol: string) => request<any[]>(/trades?symbol= + symbol),")

with open('src/api/client.ts', 'w') as f:
    f.write(text)
