# Automated Trading Strategy - Fyers Integration

## 📋 Project Overview

This is an automated positional trading system that integrates with the Fyers API to execute trades based on a sophisticated green candle pattern detection strategy. The system monitors multiple symbols simultaneously, detects specific candlestick patterns, and manages entries/exits with a multi-target and stop-loss approach.

## 🎯 Trading Strategy Logic

### Phase 1: Signal Candle Detection

The strategy identifies signal candles using a two-step approach:

1. **First Candle of Day Check:**
   - The system first checks the **first candle of the present day**
   - If the first candle is **green** (close > open), it is immediately marked as the **Signal Candle**
   - **SCH** (Signal Candle High) and **SCL** (Signal Candle Low) are recorded from this first green candle

2. **Green Candle Pattern (If First Candle is Red):**
   - If the first candle of the day is **red** (close < open), the system checks for a specific green candle pattern
   - Analyzes the last 3 candles from historical data
   - The 2nd to last candle (previous candle) must be **green** (close > open)
   - The green candle must meet two conditions:
     - Previous candle's **high** < Previous to previous candle's **high**
     - Previous candle's **low** < Previous to previous candle's **low**
   - When this pattern is detected, the green candle is marked as the **Signal Candle**
   - **SCH** (Signal Candle High) and **SCL** (Signal Candle Low) are recorded

3. **Signal Candle Identification:**
   - When a signal candle is detected, the system prints the relevant candle data for verification
   - All entry and exit levels are calculated based on the Signal Candle

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
   - **When Initial SL is hit:** All positions closed, no more trades today, fresh pattern check next day
   - If T1 is hit → Exit Tgt1Lots, move to `t1_hit` state

2. **After T1 Hit (t1_hit):**
   - SL1 or T2 can trigger
   - **If SL1 → Exit all remaining lots, all positions closed, no more trades today, fresh pattern check next day**
   - If T2 → Exit Tgt2Lots, move to `t2_hit` state

3. **After T2 Hit (t2_hit):**
   - SL2 or T3 can trigger
   - **If SL2 → Exit all remaining lots, all positions closed, no more trades today, fresh pattern check next day**
   - If T3 → Exit Tgt3Lots, move to `t3_hit` state

4. **After T3 Hit (t3_hit):**
   - SL3 or T4 can trigger
   - **If SL3 → Exit all remaining lots, all positions closed, no more trades today, fresh pattern check next day**
   - If T4 → **Exit ALL remaining lots, all positions closed, no more trades today**

5. **After T4 Hit:**
   - **When T4 is hit, ALL remaining positions are immediately closed (all lots exited)**
   - System marks position as `exited_today = True`
   - **No more trades for the present day** - monitoring stops for this symbol
   - **Fresh pattern check will start next day** - new signals can be detected tomorrow
   - Note: Tgt4Lots setting is ignored - all remaining lots are exited when T4 is hit

**Important:** When **ANY stop loss is hit** (Initial SL, SL1, SL2, SL3, or SL4), or when **T4 is hit**, all positions are closed for that symbol and **no more trades occur for the present day**. The system will start fresh pattern checks the next day.

### Trading Hours

- The strategy only operates between **StartTime** and **StopTime** (configured per symbol)
- Both signal detection and entry/exit monitoring respect these time windows
- Time format: `HH:MM` (e.g., `9:25`, `15:15`)

### Product Type Management

The strategy supports two product types, configurable per symbol:

#### 1. **Positional Trading** (`ProductType = positional`)
- Positions can carry forward to the next day
- **Fyers API Mapping:** Orders are placed with `productType: "MARGIN"` (for Futures & Options)
- **State Persistence:** Position state is saved in `state.json` and persists across days
- **No Square-Off at StopTime:** Positions are NOT automatically squared off at StopTime
- **Daily Reset Logic:**
  - **If position was exited yesterday:** Cleared for fresh pattern check today
  - **If position is still open:** Continues monitoring (carry-forward) to next day
  - **If signal detected but entry not taken:** Continues waiting for entry across days
  - Positions are monitored until all targets/SL are hit, regardless of day

#### 2. **Intraday Trading** (`ProductType = intraday`)
- Positions are squared off at StopTime
- **Fyers API Mapping:** Orders are placed with `productType: "INTRADAY"`
- **Square-Off Logic:** All remaining positions are automatically squared off when current time >= StopTime
- **Daily Reset Logic:**
  - **If position was squared off at StopTime:** Cleared for fresh pattern check next day
  - **If position was exited earlier (target/SL):** Cleared for fresh pattern check next day
  - **If signal detected but entry not taken:** Cleared for fresh pattern check next day
  - Each new day starts with a clean slate for intraday products

### Position Management

- **Multiple Symbols:** Each symbol is managed independently with its own timeframe, settings, and ProductType
- **No Duplicate Signals:** If a signal is already detected or entry is taken, new signals are ignored for that symbol
- **State Persistence:** All position data is saved in `state.json` including:
  - Entry price, remaining lots, position state
  - All target and stop loss levels
  - Signal candle information (SCH, SCL)
  - Next check time for pattern detection
  - ProductType (for proper daily reset handling)

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
| ProductType | Product type: `positional` or `intraday` | positional |

**Example:**
```csv
Symbol,Timeframe,EntryLots,SL1Points,Sl2Points,Sl3Points,Sl4Points,Tgt1Lots,Tgt2Lots,Tgt3Lots,Tgt4Lots,T2Percent,T3Percent,T4Percent,StartTime,StopTime,ProductType
NIFTY,10,4,50,50,50,50,50,50,50,50,1,1,1,9:25,15:15,positional
BANKNIFTY,5,2,30,30,30,30,25,25,25,25,0.5,0.5,0.5,9:15,15:30,intraday
```

**ProductType Options:**
- `positional`: Positions carry forward to next day, no square-off at StopTime
- `intraday`: Positions squared off at StopTime, fresh start each day

**ProductType to Fyers API Mapping:**
The system automatically maps your TradeSettings ProductType to the correct Fyers API `productType`:

| TradeSettings ProductType | Fyers API productType | Use Case |
|---------------------------|----------------------|----------|
| `intraday` | `INTRADAY` | Positions are automatically squared off at end of day (3:20 PM for equity, 3:30 PM for F&O) |
| `positional` | `MARGIN` | Positions can carry forward to next day (for Futures & Options) |

**Important Notes:**
- For **Futures & Options** (like NIFTY25DECFUT): Use `MARGIN` for positional trading
- For **Equity Stocks**: Use `CNC` for positional trading (not currently implemented, defaults to MARGIN)
- The system automatically sends the correct `productType` to Fyers API based on your TradeSettings configuration
- All orders (entry, exit, targets, stop losses) use the same `productType` as specified in TradeSettings

### 4. Run the Strategy

```bash
python main.py
```

### 5. Understanding Startup Behavior

**First Time Running (No state.json):**
```
[STATE] No previous state found - starting fresh
[STATE] All symbols will check for fresh green candle patterns
[STATE] No carry-forward positions - clean start
[STARTUP] Strategy initialized at [timestamp]
[STARTUP] Monitoring X symbols
```

**Running Next Day (With state.json from previous day):**
```
[STATE] Previous day detected: 2024-12-19 | Today: 2024-12-20
[STATE] Processing carry-forward positions...
[STATE] Carrying forward OPEN position for NIFTY
        Entry Price: 24500.50
        Remaining Lots: 2
        Position State: t2_hit
[STATE] Clearing exited position for BANKNIFTY - will check for fresh pattern
[STATE] State updated for new trading day
[STARTUP] Strategy initialized at [timestamp]
[STARTUP] Monitoring X symbols
```

**Running Same Day (With state.json from today):**
```
[STATE] Loading state from today: 2024-12-20
[STATE] Found 1 open position(s) to monitor
[STARTUP] Strategy initialized at [timestamp]
[STARTUP] Monitoring X symbols
```

## 🔄 How It Works

### Initialization

1. Loads Fyers credentials and authenticates
2. Reads trading settings from `TradeSettings.csv`
3. **State Management:**
   - Loads previous state from `state.json` (if exists)
   - **If state.json exists from previous day:**
     - Carries forward open positions (entry_taken = True)
     - Continues monitoring for targets and SL
     - Clears exited positions for fresh pattern checks
     - Prints detailed carry-forward information
   - **If state.json doesn't exist:**
     - Starts completely fresh
     - All symbols check for new green candle patterns
     - No previous positions to monitor
4. Initializes WebSocket connection for real-time LTP updates
5. Sets up per-symbol scheduling based on timeframes
6. Displays comprehensive trading status for each symbol

### Main Loop (Runs Every Second)

#### Phase 1: Signal Detection
- Checks if it's time to fetch historical data for each symbol (based on timeframe)
- Fetches OHLC data using `fetchOHLC(symbol, timeframe)`
- **First checks the first candle of the present day:**
  - If first candle is green → marks it as Signal Candle
- **If first candle is red:**
  - Analyzes last 3 candles for the green candle pattern
  - Checks if previous candle is green and meets pattern conditions
- If signal detected:
  - Calculates Entry, SL, and Target levels
  - Stores signal in state
  - Prints relevant candle data for verification
  - Schedules next check time

#### Phase 2: Entry/Exit Monitoring
- For symbols with detected signals:
  - Monitors LTP every second
  - **Intraday Square-Off Check:** If ProductType is `intraday` and current time >= StopTime, squares off all remaining positions
  - Checks entry condition: `LTP >= Entry Price`
  - Places BUY order when entry triggered
  - Recalculates all levels with actual entry price
  - Monitors for target hits and stop loss triggers
  - Places SELL orders based on state machine logic

### State Persistence & Positional Trading

- **state.json** stores:
  - Signal detection status and timestamp
  - Entry status, entry price, and entry time
  - Position state (waiting_entry, in_position, t1_hit, t2_hit, t3_hit, t4_hit)
  - Calculated levels (Entry, Initial SL, T1-T4, SL1-SL4)
  - Remaining lots after each target hit
  - Target hit status (t1_hit, t2_hit, t3_hit, t4_hit)
  - Next check time for each symbol (timeframe-based)
  - Daily exit flags (exited_today)
  - Signal candle data (SCH, SCL)

- **Daily Reset Logic (Based on ProductType):**

  **For Positional Products (`ProductType = positional`):**
  - **On new day startup:**
    - Bot checks if `state.json` exists
    - If from previous day:
      - **Open positions (entry_taken = True):** Continue monitoring, reset `exited_today` flag, carry forward to next day
      - **Exited positions (exited_today = True):** Cleared completely, fresh pattern check allowed
      - **Signals waiting for entry:** Continue waiting, reset `exited_today` flag, carry forward to next day
    - Prints detailed status of carry-forward positions
  - **Position Carry-Forward Example:**
    ```
    Day 1: Entry taken at 100, T1 hit, T2 hit, remaining lots = 2 (ProductType: positional)
    Day 2: Bot loads state.json, continues monitoring remaining 2 lots
           - Monitors for T3, T4, or SL2
           - Will book targets/SL based on Day 1 entry price
           - Position persists until all targets/SL are hit
    ```

  **For Intraday Products (`ProductType = intraday`):**
  - **Square-Off at StopTime:**
    - When current time >= StopTime, all remaining positions are automatically squared off
    - Position state is marked as `exited_today = True`
  - **On new day startup:**
    - Bot checks if `state.json` exists
    - If from previous day:
      - **All intraday positions:** Cleared completely (should have been squared off at StopTime)
      - **Signals waiting for entry:** Cleared completely, fresh pattern check allowed
    - Each new day starts with a clean slate for intraday products
  - **Intraday Example:**
    ```
    Day 1: Entry taken at 100, T1 hit, remaining lots = 3 (ProductType: intraday)
           At 15:15 (StopTime): All 3 remaining lots squared off automatically
    Day 2: Bot loads state.json, clears intraday position, checks for fresh pattern
           - New signal can be detected and new entry can be taken
    ```

## 📊 Order Execution

### Order Types
- **Entry Orders:** Market BUY orders (placed when LTP >= Entry Price)
- **Exit Orders:** Market SELL orders (placed for targets and stop losses)

### Order Logging
All orders are logged to `OrderLog.txt` with:
- Timestamp
- Order type (BUY/SELL)
- Symbol
- Quantity
- Price
- API response

## 📈 Trading Status Display

The system provides comprehensive real-time status displays for each symbol:

### Status Information Includes:

1. **Header Section:**
   - Symbol name and current LTP
   - Overall status (No Signal, Waiting for Entry, In Position, etc.)
   - Current timestamp

2. **Signal Candle Information:**
   - SCH (Signal Candle High)
   - SCL (Signal Candle Low)
   - Signal detection time

3. **Entry Information:**
   - Entry trigger price
   - Actual entry price (if entered)
   - Entry time and lots
   - Distance to entry (if waiting)

4. **Stop Loss Levels:**
   - Initial SL and distance from current price

5. **Targets & Stop Losses Table:**
   - All targets (T1-T4) with prices
   - Corresponding SL levels (SL1-SL4)
   - Exit lots for each target
   - Status (PENDING, ACTIVE, HIT)
   - Distance to target (if active)

6. **Position Summary:**
   - Remaining lots
   - Unrealized P&L (points and percentage)

7. **Trading Hours:**
   - Start/Stop times
   - Current status (ACTIVE/OUT OF HOURS)

### When Status is Displayed:
- Immediately when a signal is detected
- Immediately when entry is taken
- Every 30 seconds during active monitoring
- On any significant state change (target hit, SL triggered, etc.)

The status display uses emojis and clear formatting for easy monitoring.

## ⚠️ Important Notes

1. **Market Orders:** The system uses market orders for immediate execution. Ensure sufficient margin is available.

2. **Multiple Symbols:** Each symbol operates independently. You can monitor multiple symbols with different timeframes simultaneously.

3. **Time Normalization:** The system normalizes time to timeframe intervals. For example:
   - Current time: 13:17, Timeframe: 10 minutes
   - Normalized: 13:10
   - Next check: 13:20

4. **Trading Hours:** The strategy only operates between StartTime and StopTime. No signals or trades occur outside these hours.

5. **Product Type Management:** 
   - **Positional (`ProductType = positional`):** 
     - Positions can span multiple days
     - If a position is not exited by end of day, it will be monitored the next day
     - When you run the bot tomorrow, it will:
       - Load `state.json` and check for previous positions
       - Continue monitoring open positions from previous day
       - Book targets and SL based on previous day's entry price
       - Clear exited positions and allow fresh pattern checks
     - The system automatically handles all state persistence
   - **Intraday (`ProductType = intraday`):**
     - Positions are automatically squared off at StopTime
     - Each new day starts fresh - no positions carry forward
     - Square-off happens even if past trading hours
     - State is cleared for fresh pattern checks next day

6. **No Duplicate Entries:** Once a signal is detected or entry is taken for a symbol, no new signals are processed for that symbol until the position is exited.

7. **State File (`state.json`):** 
   - Automatically created and managed
   - **Do NOT manually edit while bot is running**
   - Contains all position information for carry-forward
   - If corrupted, delete it and bot will start fresh
   - If deleted, bot starts fresh and checks for new patterns

8. **Order Logs:** `OrderLog.txt` is cleared on each startup. Historical logs are overwritten.

9. **Fresh Start (No state.json):**
   - If `state.json` doesn't exist, bot starts completely fresh
   - All symbols from `TradeSettings.csv` will check for green candle patterns
   - No previous positions to carry forward
   - Normal pattern detection and entry logic applies

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
   - Bot will start fresh and check for new patterns

5. **Position Not Carrying Forward:**
   - Verify state.json exists and contains position data
   - Check if position was marked as `exited_today = true`
   - Ensure bot is running on the same day or next day (not same day restart)
   - Check console output for carry-forward status messages

6. **Status Display Not Showing:**
   - Status displays every 30 seconds for active positions
   - Check if signal is detected or entry is taken
   - Verify LTP is being received (check WebSocket connection)

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

**Version:** 1.2  
**Last Updated:** December 2024  
**License:** Proprietary

## 🔄 Recent Updates

### Version 1.2
- ✅ **Updated Signal Candle Logic:**
  - Now checks first candle of present day (if green = signal candle)
  - If first candle is red, checks for green candle pattern with updated conditions
  - Previous candle High < prev to previous candle's High
  - Previous candle Low < prev to previous candle's Low
- ✅ **ProductType Support:**
  - Added `ProductType` column to TradeSettings.csv
  - Supports `positional` (carry-forward) and `intraday` (square-off at StopTime)
  - Automatic mapping to Fyers API: `positional` → `MARGIN`, `intraday` → `INTRADAY`
  - All orders (entry, exit, targets, SL) use the correct Fyers productType based on TradeSettings
  - Different daily reset logic based on ProductType
- ✅ **Intraday Square-Off:**
  - Automatic square-off at StopTime for intraday products
  - Fresh pattern checks each day for intraday products
- ✅ **Enhanced Position Management:**
  - Positional products: State persists, positions carry forward
  - Intraday products: State cleared daily, fresh start each day

### Version 1.1
- ✅ Enhanced positional trading support with detailed carry-forward logic
- ✅ Comprehensive trading status display with real-time updates
- ✅ Improved state management for multi-day positions
- ✅ Better startup messages showing carry-forward positions
- ✅ Automatic handling of fresh starts when state.json doesn't exist
- ✅ Status display shows every 30 seconds for active monitoring

