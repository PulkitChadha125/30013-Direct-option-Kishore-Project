# Automated Trading Strategy - Fyers Integration

## 📋 Project Overview

This is an automated positional trading system that integrates with the Fyers API to execute trades based on a sophisticated green candle pattern detection strategy. The system monitors multiple symbols simultaneously, detects specific candlestick patterns, and manages entries/exits with a multi-target and stop-loss approach.

## 🎯 Trading Strategy Logic

### Phase 1: Signal Candle Detection

The strategy identifies a specific green candle pattern using the following criteria:

1. **Pattern Requirements:**
   - Analyzes the last 3 candles from historical data
   - The 2nd to last candle (previous candle) must be **green** (close > open)
   - The green candle must meet two conditions:
     - Green candle's **high** < Previous candle's **high**
     - Green candle's **low** > Previous candle's **low**

2. **Signal Candle Identification:**
   - When the pattern is detected, the green candle is marked as the **Signal Candle**
   - **SCH** (Signal Candle High) and **SCL** (Signal Candle Low) are recorded
   - The system prints the last 2 rows of data for verification

3. **Timing:**
   - Historical data is fetched at intervals based on each symbol's timeframe
   - Time is normalized to the lower timeframe value (e.g., if current time is 13:17 and timeframe is 10 minutes, it normalizes to 13:10)
   - Next check time = Normalized time + Timeframe minutes (e.g., 13:20 for 10-minute timeframe)
   - Each symbol has independent scheduling based on its timeframe

### Phase 2: Entry and Exit Management

Once a signal candle is detected, the system enters monitoring mode:

#### Entry Calculation:
- **Entry Price** = SCH + (√(SCH) × 26.11%)
- Entry is triggered when **LTP >= Entry Price**
- On entry, a **BUY order** is placed with the specified EntryLots quantity

#### Level Calculations (After Entry):
- **Initial Stop Loss** = SCL - (√(SCL) × 26.11%)
- **Target 1 (T1)** = Entry Price (EP) + 13.06%
- **Target 2 (T2)** = EP + T2Percent%
- **Target 3 (T3)** = EP + T3Percent%
- **Target 4 (T4)** = EP + T4Percent%

#### Stop Loss Levels:
- **SL1** = T1 - SL1Points
- **SL2** = T2 - SL2Points
- **SL3** = T3 - SL3Points
- **SL4** = T4 - SL4Points

#### Exit State Machine:

The system follows a sequential state machine for exits:

1. **Initial State (in_position):**
   - Only Initial SL can trigger → Exit all remaining lots
   - If T1 is hit → Exit Tgt1Lots, move to `t1_hit` state

2. **After T1 Hit (t1_hit):**
   - SL1 or T2 can trigger
   - If SL1 → Exit all remaining lots
   - If T2 → Exit Tgt2Lots, move to `t2_hit` state

3. **After T2 Hit (t2_hit):**
   - SL2 or T3 can trigger
   - If SL2 → Exit all remaining lots
   - If T3 → Exit Tgt3Lots, move to `t3_hit` state

4. **After T3 Hit (t3_hit):**
   - SL3 or T4 can trigger
   - If SL3 → Exit all remaining lots
   - If T4 → Exit Tgt4Lots, move to `t4_hit` state

5. **After T4 Hit (t4_hit):**
   - Only SL4 can trigger → Exit all remaining lots

### Trading Hours

- The strategy only operates between **StartTime** and **StopTime** (configured per symbol)
- Both signal detection and entry/exit monitoring respect these time windows
- Time format: `HH:MM` (e.g., `9:25`, `15:15`)

### Position Management

- **Multiple Symbols:** Each symbol is managed independently with its own timeframe and settings
- **No Duplicate Signals:** If a signal is already detected or entry is taken, new signals are ignored for that symbol
- **Position Carry-Forward:** Open positions persist across bot restarts via `state.json`
- **Daily Reset:** Positions exited during the day won't trigger new trades that day. Fresh pattern checks resume the next day

## 📁 Project Structure

```
.
├── main.py                  # Main strategy implementation
├── FyresIntegration.py      # Fyers API integration functions
├── TradeSettings.csv        # Trading parameters for each symbol
├── FyersCredentials.csv      # Fyers API credentials
├── state.json               # Position state persistence (auto-generated)
├── OrderLog.txt            # Order execution logs (auto-generated)
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## 🚀 Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Required packages:
- `fyers-apiv3` - Fyers API client
- `pyotp` - TOTP authentication
- `requests` - HTTP requests
- `pandas` - Data manipulation
- `pytz` - Timezone handling
- `numpy` - Numerical operations
- `polars` - Fast dataframes
- `polars-talib` - Technical analysis

### 2. Configure Fyers Credentials

Create `FyersCredentials.csv` with the following structure:

```csv
Title,Value
client_id,YOUR_CLIENT_ID
secret_key,YOUR_SECRET_KEY
redirect_uri,YOUR_REDIRECT_URI
grant_type,authorization_code
response_type,code
state,None
totpkey,YOUR_TOTP_KEY
FY_ID,YOUR_FYERS_ID
PIN,YOUR_PIN
```

### 3. Configure Trading Settings

Edit `TradeSettings.csv` with your trading parameters:

| Column | Description | Example |
|--------|-------------|---------|
| Symbol | Trading symbol (NSE format) | NIFTY |
| Timeframe | Candle timeframe in minutes | 10 |
| EntryLots | Number of lots for entry | 4 |
| SL1Points | Stop loss points below T1 | 50 |
| Sl2Points | Stop loss points below T2 | 50 |
| Sl3Points | Stop loss points below T3 | 50 |
| Sl4Points | Stop loss points below T4 | 50 |
| Tgt1Lots | Lots to exit at T1 | 50 |
| Tgt2Lots | Lots to exit at T2 | 50 |
| Tgt3Lots | Lots to exit at T3 | 50 |
| Tgt4Lots | Lots to exit at T4 | 50 |
| T2Percent | Percentage for T2 calculation | 1 |
| T3Percent | Percentage for T3 calculation | 1 |
| T4Percent | Percentage for T4 calculation | 1 |
| StartTime | Trading start time (HH:MM) | 9:25 |
| StopTime | Trading stop time (HH:MM) | 15:15 |

**Example:**
```csv
Symbol,Timeframe,EntryLots,SL1Points,Sl2Points,Sl3Points,Sl4Points,Tgt1Lots,Tgt2Lots,Tgt3Lots,Tgt4Lots,T2Percent,T3Percent,T4Percent,StartTime,StopTime
NIFTY,10,4,50,50,50,50,50,50,50,50,1,1,1,9:25,15:15
```

### 4. Run the Strategy

```bash
python main.py
```

## 🔄 How It Works

### Initialization

1. Loads Fyers credentials and authenticates
2. Reads trading settings from `TradeSettings.csv`
3. Loads previous state from `state.json` (if exists)
4. Initializes WebSocket connection for real-time LTP updates
5. Sets up per-symbol scheduling based on timeframes

### Main Loop (Runs Every Second)

#### Phase 1: Signal Detection
- Checks if it's time to fetch historical data for each symbol (based on timeframe)
- Fetches OHLC data using `fetchOHLC(symbol, timeframe)`
- Analyzes last 3 candles for the green candle pattern
- If pattern detected:
  - Calculates Entry, SL, and Target levels
  - Stores signal in state
  - Prints last 2 candles for verification
  - Schedules next check time

#### Phase 2: Entry/Exit Monitoring
- For symbols with detected signals:
  - Monitors LTP every second
  - Checks entry condition: `LTP >= Entry Price`
  - Places BUY order when entry triggered
  - Recalculates all levels with actual entry price
  - Monitors for target hits and stop loss triggers
  - Places SELL orders based on state machine logic

### State Persistence

- **state.json** stores:
  - Signal detection status
  - Entry status and price
  - Position state (waiting_entry, in_position, t1_hit, etc.)
  - Calculated levels (Entry, SL, Targets)
  - Remaining lots
  - Next check time for each symbol
  - Daily exit flags

- **Daily Reset Logic:**
  - On new day, positions exited yesterday are cleared
  - Open positions continue to be monitored
  - Fresh pattern checks resume for cleared positions

## 📊 Order Execution

### Order Types
- **Entry Orders:** Market BUY orders
- **Exit Orders:** Market SELL orders

### Order Logging
All orders are logged to `OrderLog.txt` with:
- Timestamp
- Order type (BUY/SELL)
- Symbol
- Quantity
- Price
- API response

## ⚠️ Important Notes

1. **Market Orders:** The system uses market orders for immediate execution. Ensure sufficient margin is available.

2. **Multiple Symbols:** Each symbol operates independently. You can monitor multiple symbols with different timeframes simultaneously.

3. **Time Normalization:** The system normalizes time to timeframe intervals. For example:
   - Current time: 13:17, Timeframe: 10 minutes
   - Normalized: 13:10
   - Next check: 13:20

4. **Trading Hours:** The strategy only operates between StartTime and StopTime. No signals or trades occur outside these hours.

5. **Position Carry-Forward:** If a position is not exited by end of day, it will be monitored the next day. The system automatically handles state persistence.

6. **No Duplicate Entries:** Once a signal is detected or entry is taken for a symbol, no new signals are processed for that symbol until the position is exited.

7. **State File:** The `state.json` file is automatically created and managed. Do not manually edit it while the bot is running.

8. **Order Logs:** `OrderLog.txt` is cleared on each startup. Historical logs are overwritten.

## 🔧 Troubleshooting

### Common Issues

1. **Authentication Errors:**
   - Verify FyersCredentials.csv has correct values
   - Ensure TOTP key is valid
   - Check if Fyers account is active

2. **No Signals Detected:**
   - Verify historical data is available for the symbol
   - Check if trading hours are correct
   - Ensure timeframe matches the symbol's trading pattern

3. **Orders Not Placing:**
   - Check margin availability
   - Verify symbol format (should be NSE:SYMBOL)
   - Check OrderLog.txt for error messages

4. **State Issues:**
   - If state.json is corrupted, delete it and restart
   - The system will create a fresh state file

## 📝 Formula Reference

### Entry Calculation
```
Entry = SCH + (√(SCH) × 0.2611)
```

### Initial Stop Loss
```
Initial SL = SCL - (√(SCL) × 0.2611)
```

### Target Calculations
```
T1 = EP + (EP × 0.1306)
T2 = EP + (EP × T2Percent / 100)
T3 = EP + (EP × T3Percent / 100)
T4 = EP + (EP × T4Percent / 100)
```

### Stop Loss Calculations
```
SL1 = T1 - SL1Points
SL2 = T2 - SL2Points
SL3 = T3 - SL3Points
SL4 = T4 - SL4Points
```

## 🔐 Security

- **Credentials:** Never commit `FyersCredentials.csv` to version control
- **API Keys:** Keep your Fyers API credentials secure
- **State File:** Contains position information - handle with care

## 📞 Support

For issues or questions:
1. Check `OrderLog.txt` for execution details
2. Review console output for error messages
3. Verify configuration files are correctly formatted

## ⚖️ Disclaimer

This trading system is for educational and research purposes. Trading involves substantial risk of loss. Always:
- Test thoroughly in paper trading mode first
- Understand the strategy completely before live trading
- Monitor positions actively
- Ensure sufficient risk management
- Comply with all applicable regulations

**Use at your own risk. The authors are not responsible for any trading losses.**

---

**Version:** 1.0  
**Last Updated:** 2024  
**License:** Proprietary

