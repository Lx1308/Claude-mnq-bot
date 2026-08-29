with open('src/api/client.ts', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "trades:" in line:
        lines[i] = "  trades: (symbol: string) => request<any[]>('/trades?symbol=' + symbol),\n"

with open('src/api/client.ts', 'w') as f:
    f.writelines(lines)
