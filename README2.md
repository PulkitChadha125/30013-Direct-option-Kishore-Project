# Trading Strategy Documentation

## Overview

This is an automated trading strategy that detects buy/sell signals based on candlestick patterns and executes trades with predefined entry, target, and stop-loss levels. The strategy is designed to take **one trade per day** per symbol and operates on configurable timeframes.

## Strategy Architecture

### Core Components

1. **Signal Detection Module**: Identifies buy/sell signals based on candlestick patterns
2. **Entry Price Calculator**: Calculates entry prices based on market type (IO/UL)
3. **Level Calculator**: Computes all target and stop-loss levels
4. **State Management**: Tracks positions and trading state across sessions
5. **Timeframe-Based Execution**: Runs checks at regular intervals based on timeframe

---

## How the Strategy Works

### 1. Initialization

- Loads trading settings from `TradeSettings.csv`
- Authenticates with Fyers API
- Initializes WebSocket for real-time market data (LTP)
- Loads previous state from `state.json` (if exists)
- Resets state for new trading day

### 2. Timeframe-Based Signal Checking

The strategy runs checks at **timeframe intervals** starting from `StartTime`:

- **Example**: If `StartTime = 9:30` and `Timeframe = 5 minutes`
  - First check: 9:30:01
  - Next checks: 9:35, 9:40, 9:45, 9:50, etc.
- If started at 9:33, next runs at: 9:35, 9:40, 9:45, etc.

At each check:
1. Fetches historical OHLC data
2. Filters out the current/forming candle
3. Examines the **previous 2 completed candles**
4. Checks for signal patterns
5. Prints OHLC of the 2 candles being checked

### 3. Signal Detection Logic

#### BUY Signal Pattern

At each timeframe check (e.g., 9:30), the strategy examines the last 2 completed candles (e.g., 9:25 and 9:20):

**Conditions for BUY Signal:**
- Current candle (9:25) is **GREEN** (Close > Open)
- Current candle **High < Previous candle High** (9:25 High < 9:20 High)
- Current candle **Low < Previous candle Low** (9:25 Low < 9:20 Low)

**Signal Candle High (SCH)**: The high of the green signal candle (9:25)

#### SELL Signal Pattern

**Conditions for SELL Signal:**
- Current candle (9:25) is **RED** (Close < Open)
- Current candle **High > Previous candle High** (9:25 High > 9:20 High)
- Current candle **Low > Previous candle Low** (9:25 Low > 9:20 Low)

**Signal Candle Low (SCH)**: The low of the red signal candle (9:25)

### 4. Entry Price Calculation

Entry price is calculated based on **Market Type** from `TradeSettings.csv`:

#### For IO (Index Options)

**BUY Entry:**
```
Entry = SCH + (√(SCH) × 26.11%)
```
Where SCH = Signal Candle High

**SELL Entry:**
```
Entry = SCH - (√(SCH) × 26.11%)
```
Where SCH = Signal Candle Low

#### For UL (Underlying/Stock/Futures/Commodity)

**BUY Entry:**
```
Entry = SCH + (∛(SCH) × 26.11%)
```
Where SCH = Signal Candle High

**SELL Entry:**
```
Entry = SCH - (∛(SCH) × 26.11%)
```
Where SCH = Signal Candle Low

### 5. Target and Stop-Loss Calculations

#### For BUY Signals

**Targets (Above Entry):**
- **T1** = Entry Price (EP) + T1Percent%
- **T2** = EP + T2Percent%
- **T3** = EP + T3Percent%
- **T4** = EP + T4Percent%

**Stop Losses (Below Entry/Targets):**
- **SL1** = EP - SL1Points (exits all lots)
- **SL2** = T1 - SL2Points (exits all remaining lots)
- **SL3** = T2 - SL3Points (exits all remaining lots)
- **SL4** = T3 - SL4Points (exits all remaining lots)

#### For SELL Signals

**Targets (Below Entry):**
- **T1** = Entry Price (EP) - T1Percent%
- **T2** = EP - T2Percent%
- **T3** = EP - T3Percent%
- **T4** = EP - T4Percent%

**Stop Losses (Above Entry/Targets):**
- **SL1** = EP + SL1Points (exits all lots)
- **SL2** = T1 + SL2Points (exits all remaining lots)
- **SL3** = T2 + SL3Points (exits all remaining lots)
- **SL4** = T3 + SL4Points (exits all remaining lots)

### 6. Exit Logic

- **Targets**: Partial exits based on `Tgt1Lots`, `Tgt2Lots`, `Tgt3Lots`, `Tgt4Lots`
- **Stop Losses**: Exit **ALL remaining lots** when any SL is hit
- **One Trade Per Day**: Once a signal is detected or entry is taken, no new signals are checked for that symbol on the same day

---

## Trading Logic Implementation

### Function: `check_signal_for_symbol()`

**Purpose**: Detects buy/sell signals by examining candlestick patterns

**Process**:
1. Validates trading hours (StartTime to StopTime)
2. Checks if signal/entry already detected today (one trade per day)
3. Fetches historical OHLC data
4. Filters completed candles (excludes forming candle)
5. Gets last 2 completed candles
6. Prints OHLC of both candles
7. Checks for BUY pattern:
   - Green candle with High < Prev High and Low < Prev Low
8. Checks for SELL pattern:
   - Red candle with High > Prev High and Low > Prev Low
9. If signal detected:
   - Calculates entry price using `calculate_entry_price()`
   - Calculates all levels using `calculate_levels()`
   - Stores signal state in `positions_state`
   - Logs comprehensive details to console and `OrderLog.txt`

### Function: `calculate_entry_price()`

**Parameters**:
- `signal_candle_value`: SCH (high for BUY, low for SELL)
- `direction`: 'BUY' or 'SELL'
- `market_type`: 'IO' or 'UL'

**Returns**: Entry price (float)

**Logic**:
- **IO**: Uses square root (√)
- **UL**: Uses cube root (∛)
- Applies 26.11% multiplier
- Adds for BUY, subtracts for SELL

### Function: `calculate_levels()`

**Parameters**:
- `entry_price`: Calculated entry price
- `direction`: 'BUY' or 'SELL'
- `t1_percent` to `t4_percent`: Target percentages
- `sl1_points` to `sl4_points`: Stop loss points

**Returns**: Dictionary with T1, T2, T3, T4, SL1, SL2, SL3, SL4

**Logic**:
- **BUY**: Targets above entry (+%), SLs below entry (-points)
- **SELL**: Targets below entry (-%), SLs above entry (+points)

### Function: `main_strategy()`

**Purpose**: Main execution loop that orchestrates signal detection

**Process**:
1. Updates LTP data from WebSocket
2. Loops through each symbol in `result_dict`
3. Checks if it's time to run signal check (timeframe-based)
4. Calls `check_signal_for_symbol()` when time matches
5. Updates `next_check_time` for next interval
6. Saves state after each check

---

## Configuration

### TradeSettings.csv Structure

| Column | Description | Example |
|--------|-------------|---------|
| Symbol | Trading symbol | NIFTY25DEC26200CE |
| Timeframe | Candle timeframe in minutes | 1, 5, 15 |
| EntryLots | Number of lots to enter | 300 |
| SL1Points | Stop loss 1 points | 5 |
| Sl2Points | Stop loss 2 points | 5 |
| Sl3Points | Stop loss 3 points | 5 |
| Sl4Points | Stop loss 4 points | 5 |
| Tgt1Lots | Lots to exit at T1 | 75 |
| Tgt2Lots | Lots to exit at T2 | 75 |
| Tgt3Lots | Lots to exit at T3 | 75 |
| Tgt4Lots | Lots to exit at T4 | 75 |
| T1Percent | Target 1 percentage | 13.6 |
| T2Percent | Target 2 percentage | 13.6 |
| T3Percent | Target 3 percentage | 15 |
| T4Percent | Target 4 percentage | 16 |
| StartTime | Trading start time (HH:MM) | 13:15 |
| StopTime | Trading stop time (HH:MM) | 15:30 |
| Market | Market type: IO or UL | IO |

### Example Configuration

```csv
Symbol,Timeframe,EntryLots,SL1Points,Sl2Points,Sl3Points,Sl4Points,Tgt1Lots,Tgt2Lots,Tgt3Lots,Tgt4Lots,T1Percent,T2Percent,T3Percent,T4Percent,StartTime,StopTime,Market
NIFTY25DEC26200CE,1,300,5,5,5,5,75,75,75,75,13.6,13.6,15,16,13:15,15:30,IO
```

---

## State Management

### State Storage (`state.json`)

The strategy maintains state in `state.json` with the following structure:

```json
{
  "date": "2024-12-25",
  "positions": {
    "SYMBOL_0": {
      "signal_detected": true,
      "signal_time": "2024-12-25T13:20:00",
      "direction": "BUY",
      "SCH": 26200.50,
      "Entry": 26450.25,
      "T1": 30100.00,
      "T2": 30200.00,
      "T3": 30300.00,
      "T4": 30400.00,
      "SL1": 26445.25,
      "SL2": 30095.00,
      "SL3": 30195.00,
      "SL4": 30295.00,
      "entry_taken": false,
      "position_state": "waiting_entry",
      "remaining_lots": 300,
      "market_type": "IO"
    }
  }
}
```

### State Fields

- `signal_detected`: Boolean indicating if signal was found
- `direction`: 'BUY' or 'SELL'
- `SCH`: Signal Candle High/Low value
- `Entry`: Calculated entry price
- `T1` to `T4`: Target levels
- `SL1` to `SL4`: Stop loss levels
- `entry_taken`: Boolean indicating if entry order was placed
- `position_state`: Current position state (waiting_entry, in_position, etc.)
- `remaining_lots`: Number of lots still in position
- `exited_today`: Boolean indicating if position was exited today

### Daily Reset Logic

- On new trading day, state is reset for fresh pattern checks
- One trade per day per symbol is enforced
- Previous day's exited positions are cleared

---

## File Structure

```
project/
├── Strategy.py              # Main strategy implementation
├── FyresIntegration.py      # Fyers API integration
├── TradeSettings.csv        # Trading configuration
├── FyersCredentials.csv     # API credentials
├── state.json               # Position state storage
├── OrderLog.txt             # Trading activity logs
├── data/                    # Historical OHLC data (CSV files)
│   ├── NSE_SYMBOL1.csv
│   └── NSE_SYMBOL2.csv
└── README2.md              # This documentation
```

---

## Logging

### Console Output

- Signal detection messages
- OHLC of candles being checked
- Entry price and level calculations
- Error messages and tracebacks

### OrderLog.txt

Comprehensive logging includes:
- Signal detection timestamps
- Signal candle details (OHLC)
- Entry price calculations
- All target and stop-loss levels
- Trading activity

**Format**: `[YYYY-MM-DD HH:MM:SS] Message`

---

## Key Features

1. **One Trade Per Day**: Each symbol can only have one signal/entry per trading day
2. **Timeframe-Based Execution**: Checks run at regular intervals based on timeframe
3. **Pattern Recognition**: Detects specific candlestick patterns for buy/sell signals
4. **Market Type Support**: Different entry calculations for IO (Index Options) and UL (Underlying)
5. **State Persistence**: Maintains state across sessions via `state.json`
6. **Comprehensive Logging**: Detailed logs in console and `OrderLog.txt`
7. **Real-Time Data**: Uses WebSocket for live LTP updates
8. **Historical Data Storage**: Saves OHLC data to CSV files in `data/` folder

---

## Execution Flow

```
1. Initialize
   ├── Load credentials
   ├── Load TradeSettings.csv
   ├── Load state.json
   └── Initialize WebSocket

2. Main Loop (runs every 1 second)
   ├── Update LTP data
   └── For each symbol:
       ├── Check if time to run (timeframe-based)
       ├── If yes:
       │   ├── Fetch OHLC data
       │   ├── Check signal patterns
       │   ├── If signal found:
       │   │   ├── Calculate entry price
       │   │   ├── Calculate levels
       │   │   ├── Store state
       │   │   └── Log details
       │   └── Update next_check_time
       └── Save state

3. Entry/Exit Monitoring (Future Phase)
   ├── Monitor LTP vs Entry price
   ├── Place entry order when price reached
   ├── Monitor LTP vs Targets/SLs
   └── Place exit orders when levels hit
```

---

## Mathematical Formulas

### Entry Price Calculation

**IO (Index Options) - BUY:**
```
Entry = SCH + (√(SCH) × 0.2611)
```

**IO (Index Options) - SELL:**
```
Entry = SCH - (√(SCH) × 0.2611)
```

**UL (Underlying) - BUY:**
```
Entry = SCH + (SCH^(1/3) × 0.2611)
```

**UL (Underlying) - SELL:**
```
Entry = SCH - (SCH^(1/3) × 0.2611)
```

### Target Calculations

**BUY:**
```
T1 = EP × (1 + T1Percent/100)
T2 = EP × (1 + T2Percent/100)
T3 = EP × (1 + T3Percent/100)
T4 = EP × (1 + T4Percent/100)
```

**SELL:**
```
T1 = EP × (1 - T1Percent/100)
T2 = EP × (1 - T2Percent/100)
T3 = EP × (1 - T3Percent/100)
T4 = EP × (1 - T4Percent/100)
```

### Stop Loss Calculations

**BUY:**
```
SL1 = EP - SL1Points
SL2 = T1 - SL2Points
SL3 = T2 - SL3Points
SL4 = T3 - SL4Points
```

**SELL:**
```
SL1 = EP + SL1Points
SL2 = T1 + SL2Points
SL3 = T2 + SL3Points
SL4 = T3 + SL4Points
```

---

## Notes

- The strategy only checks for signals during trading hours (StartTime to StopTime)
- Only completed candles are analyzed (forming candles are excluded)
- Historical OHLC data is saved to CSV files for reference
- State is automatically saved after each signal detection
- The strategy enforces one trade per day per symbol
- Entry/Exit monitoring logic will be implemented in the next phase

---

## Future Enhancements

1. **Entry/Exit Monitoring**: Real-time monitoring of LTP vs Entry price and Targets/SLs
2. **Order Placement**: Automatic order placement when conditions are met
3. **Position Management**: Track and manage open positions
4. **Risk Management**: Additional risk controls and validations
5. **Performance Analytics**: Track win rate, profit/loss, etc.

---

*Last Updated: December 2024*

