# Valuation Rules

Valuation is not a prediction of what a stock will do. It is a framework for understanding what you are paying for and how much room for error you have.

---

## 1. Which Method to Use — and When

| Method | Best for | Not suitable for |
|---|---|---|
| **P/E ratio** | Stable, profitable, asset-light businesses | Banks, cyclicals, loss-making companies |
| **P/Book** | Banks, NBFCs, capital-intensive companies | Asset-light, services businesses |
| **EV/EBITDA** | Capital-intensive, cyclicals, comparing across capital structures | Financial companies (EBITDA is meaningless) |
| **DCF** | Predictable, long-duration businesses | Cyclicals, early-stage, unpredictable cash flows |
| **EV/Sales** | High-growth, pre-profit companies | Anything mature and profitable (use earnings-based) |
| **PEG ratio** | Growth companies where P/E looks optically high | Cyclicals, value stocks, capital-intensive businesses |
| **Dividend Yield** | Mature, cash-generative, low-growth companies | Growth companies reinvesting all earnings |
| **NAV** | Real estate developers, holding companies | Operating businesses |

---

## 2. P/E Ratio — Rules and Traps

### The basic formula:
$$P/E = \frac{\text{Market Price per Share}}{\text{Earnings per Share (TTM or Forward)}}$$

### Rules:
- Always compare P/E to the **company's own historical range** (5-year band) before comparing to sector
- Use **normalised earnings** for cyclical companies — peak earnings make cyclicals look cheap when they are actually expensive
- A low P/E on a deteriorating business is a **value trap**
- Forward P/E is only as good as the estimate — treat analyst consensus with scepticism during macro inflections

### Sector P/E benchmarks (India, long-run averages):
| Sector | Low | Mid | High |
|---|---|---|---|
| FMCG / Consumer Staples | 30x | 45x | 65x |
| IT Services | 18x | 25x | 35x |
| Pharma | 18x | 28x | 40x |
| Private Banks | 12x | 18x | 28x |
| Specialty Chemicals | 22x | 35x | 55x |
| Autos (OEM) | 10x | 18x | 28x |
| Capital Goods / Infra | 12x | 22x | 35x |
| PSU Banks | 5x | 10x | 15x |

---

## 3. EV/EBITDA — Rules and Traps

### The formula:
$$EV/EBITDA = \frac{\text{Enterprise Value}}{\text{EBITDA}}$$
$$EV = \text{Market Cap} + \text{Net Debt} + \text{Minority Interest} - \text{Associates}$$

### Why EV/EBITDA:
- Removes capital structure distortions (debt vs. equity-funded)
- Useful for comparing companies with different D/A profiles
- Does not remove capex — therefore misleading for high-capex businesses without adjusting for maintenance capex

### Sector benchmarks:
| Sector | Fair Range |
|---|---|
| FMCG | 25–40x |
| IT Services | 15–22x |
| Specialty Chemicals | 15–25x |
| Capital Goods | 10–16x |
| Cement | 10–14x |
| Autos | 8–12x |
| Oil & Gas (refining) | 5–8x |
| Real Estate | Prefer NAV |

---

## 4. P/Book — Rules for Financial Companies

$$P/B = \frac{\text{Market Cap}}{\text{Book Value (Shareholders' Equity)}}$$

### Justified P/B formula:
$$\text{Justified } P/B = \frac{RoE - g}{CoE - g}$$

Where:  
- RoE = sustainable return on equity  
- g = long-run earnings growth  
- CoE = cost of equity (typically 13–15% for India)

**Example:** A bank with 18% RoE, 12% growth, 14% CoE → Justified P/B = (18-12)/(14-12) = **3.0x**

### Benchmarks:
| Bank Type | Fair P/B |
|---|---|
| High-quality private bank (RoE >18%) | 2.5–4.0x |
| Mid-quality private bank (RoE 12–18%) | 1.5–2.5x |
| PSU bank (RoE 8–12%) | 0.8–1.5x |
| NBFC (RoE >18%) | 3.0–5.0x |

---

## 5. DCF — Rules and Pitfalls

### Structure:
- **Phase 1 (Years 1–5):** Explicit forecast period — model revenue, margins, capex, working capital
- **Phase 2 (Years 6–10):** Fade revenue growth toward terminal rate
- **Terminal value:** Gordon Growth Model — `FCF × (1+g) / (WACC - g)`

### Critical assumptions for India:
- **WACC:** 12–14% for large-cap; 14–16% for mid-cap; 16%+ for small-cap
- **Risk-free rate:** Use 10-year G-Sec yield (~7.0–7.5%)
- **Equity risk premium:** 5–6% for India
- **Terminal growth:** 4–6% (do NOT use >GDP nominal growth = ~10–11% in India)

### DCF Rules:
1. Terminal value typically accounts for 60–80% of DCF value — be conservative with terminal growth
2. Sensitivity-test WACC ±1% and terminal growth ±0.5% — if the fair value swings wildly, the business is not DCF-able
3. DCF is most reliable for **capital-light, predictable FCF** businesses — IT, FMCG, pharma
4. For cyclicals, use **mid-cycle FCF**, not peak FCF

---

## 6. PEG Ratio — Growth-Adjusted Valuation

$$PEG = \frac{P/E}{\text{EPS Growth Rate (\% per year)}}$$

### Rules:
- PEG < 1.0 → potentially undervalued for a growth company
- PEG 1.0–1.5 → fairly valued
- PEG > 2.0 → expensive relative to growth
- **Use 3–5 year forward earnings CAGR, not trailing growth** (past growth may not persist)
- PEG is meaningless for cyclicals, financials, and low-growth companies

---

## 7. Margin of Safety

Popularised by Benjamin Graham — the difference between intrinsic value and market price is your cushion for being wrong.

**Guidelines:**
- For high-quality, predictable businesses: 20–25% margin of safety is adequate
- For uncertain or cyclical businesses: 40–50% margin of safety required
- For turnaround or distressed situations: 50%+ margin of safety — and even then, be cautious

**The margin of safety IS the return in many cases.** A business bought at 50% of fair value can double even without any improvement in fundamentals.

---

## 8. Valuation Sanity Checks

Before finalising a valuation call, answer these:

1. **Am I using normalised or peak earnings?** — Cyclicals at peak earnings always look cheap
2. **Is the market pricing in bad news that is already in the stock?** — Cheap for a reason vs. cheap for no reason
3. **What is the market's implied growth rate at current price?** — Back-solve from DCF to find what growth is assumed
4. **How does this compare to the company's own 5-year median multiple?** — Premium/discount to history and why
5. **What could make this a zero?** — Permanently impaired businesses deserve low multiples even at "cheap" prices

---

## 9. Common Valuation Mistakes

| Mistake | Why it is wrong |
|---|---|
| Using peak earnings for cyclicals | Makes expensive stocks appear cheap |
| Ignoring net debt in P/E comparisons | Two companies at 20x P/E but different leverage are not equal |
| Anchoring to purchase price | Market doesn't care what you paid |
| Confusing cheap with value | A declining business at 5x P/E can still be expensive |
| Discounting the terminal value too lightly | Small changes to terminal assumptions drive huge changes in fair value |
| Using consensus estimates uncritically | Consensus is wrong at macro turning points — almost by definition |
