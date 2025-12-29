import pandas as pd
from datetime import datetime, timedelta, time as dt_time
import polars as pl
import polars_talib as plta
import json
import time
import traceback
import sys
import os
import pytz
from FyresIntegration import *

def normalize_time_to_timeframe(current_time, timeframe_minutes):
    """
    Normalize time to the specified timeframe interval.
    
    Args:
        current_time: datetime object (current time)
        timeframe_minutes: int (timeframe in minutes, e.g., 5 for 5-minute intervals)
    
    Returns:
        datetime: normalized time rounded down to the nearest timeframe interval
    """
    # Calculate how many complete timeframe intervals have passed
    intervals_passed = current_time.minute // timeframe_minutes
    
    # Calculate the normalized minute (round down to nearest timeframe)
    normalized_minute = intervals_passed * timeframe_minutes
    
    # Create normalized time (set seconds and microseconds to 0)
    normalized_time = current_time.replace(
        minute=normalized_minute, 
        second=0, 
        microsecond=0
    )
    
    return normalized_time







def get_api_credentials_Fyers():
    credentials_dict_fyers = {}
    try:
        df = pd.read_csv('FyersCredentials.csv')
        for index, row in df.iterrows():
            title = row['Title']
            value = row['Value']
            credentials_dict_fyers[title] = value
    except pd.errors.EmptyDataError:
        print("The CSV FyersCredentials.csv file is empty or has no data.")
    except FileNotFoundError:
        print("The CSV FyersCredentials.csv file was not found.")
    except Exception as e:
        print("An error occurred while reading the CSV FyersCredentials.csv file:", str(e))
    return credentials_dict_fyers





def delete_file_contents(file_name):
    try:
        # Open the file in write mode, which truncates it (deletes contents)
        with open(file_name, 'w') as file:
            file.truncate(0)
        print(f"Contents of {file_name} have been deleted.")
    except FileNotFoundError:
        print(f"File {file_name} not found.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")

          

def write_to_order_logs(message):
    with open('OrderLog.txt', 'a') as file:  # Open the file in append mode
        # Skip timestamp for empty lines (used as separators)
        if message.strip() == "":
            file.write('\n')
        else:
            timestamp = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')
            file.write(f"[{timestamp}] {message}\n")

def load_state():
    """Load state from state.json file - returns positions even if from different day"""
    try:
        with open('state.json', 'r') as f:
            content = f.read().strip()
            # Check if file is empty
            if not content:
                print("[STATE] state.json is empty - starting fresh")
                return {}, None
            state = json.loads(content)
            return state.get('positions', {}), state.get('date')
    except FileNotFoundError:
        print("[STATE] state.json not found - starting fresh")
        return {}, None
    except json.JSONDecodeError as e:
        print(f"[STATE] Error parsing state.json (invalid JSON): {e}")
        print("[STATE] Starting fresh - consider backing up or fixing state.json if needed")
        return {}, None
    except Exception as e:
        print(f"[STATE] Error loading state: {e}")
        print("[STATE] Starting fresh")
        return {}, None

def save_state(positions_state):
    """Save state to state.json file"""
    try:
        state = {
            'date': datetime.now().date().isoformat(),
            'positions': positions_state
        }
        with open('state.json', 'w') as f:
            json.dump(state, f, indent=2, default=str)
    except Exception as e:
        print(f"Error saving state: {e}")

def is_time_between(start_time_str, stop_time_str, current_time=None):
    """Check if current time is between start_time and stop_time"""
    if current_time is None:
        current_time = datetime.now().time()
    
    try:
        # Parse time strings (format: "HH:MM")
        start_hour, start_min = map(int, start_time_str.split(':'))
        stop_hour, stop_min = map(int, stop_time_str.split(':'))
        
        start = dt_time(start_hour, start_min)
        stop = dt_time(stop_hour, stop_min)
        
        if start <= stop:
            # Normal case: start < stop (e.g., 9:25 to 15:15)
            return start <= current_time <= stop
        else:
            # Overnight case: start > stop (e.g., 22:00 to 2:00)
            return current_time >= start or current_time <= stop
    except Exception as e:
        print(f"Error parsing time: {e}")
        return True  # Default to True if parsing fails

def check_signal_candle(df, start_time_str, timeframe_minutes):
    """
    Check for signal candle based on new logic:
    1. Calculate first candle time = StartTime - timeframe (e.g., 9:30 - 15 mins = 9:15)
    2. Check if that first candle is green - if yes, it's signal candle
    3. If first candle is red, wait for next green candle that meets pattern:
       - Green candle (close > open)
       - Previous candle High < prev to previous candle's High
       - Previous candle Low < prev to previous candle's Low
    Returns (is_signal, signal_candle_data, first_candle_info) where:
        - signal_candle_data is dict with high, low, open, close (if signal found)
        - first_candle_info is dict with 'color', 'date', 'open', 'high', 'low', 'close' for the first candle
    """
    if len(df) < 2:
        return False, None, None
    
    # Calculate the expected first candle time = StartTime - timeframe
    try:
        start_hour, start_min = map(int, start_time_str.split(':'))
        today = datetime.now(pytz.timezone('Asia/Kolkata')).date()
        start_time_today = pytz.timezone('Asia/Kolkata').localize(datetime.combine(today, dt_time(start_hour, start_min)))
        first_candle_time = start_time_today - timedelta(minutes=timeframe_minutes)
    except Exception as e:
        print(f"Error parsing StartTime: {e}")
        return False, None, None
    
    # Sort dataframe by date to ensure chronological order
    df_sorted = df.sort_values('date').copy()
    df_sorted = df_sorted.reset_index(drop=True)
    
    # Find the exact first candle at first_candle_time
    # Convert to same timezone-aware format for comparison
    df_sorted['date_dt'] = pd.to_datetime(df_sorted['date'])
    first_candle_exact = df_sorted[df_sorted['date_dt'] == first_candle_time]
    
    if len(first_candle_exact) > 0:
        # Found exact match
        first_candle_to_check = first_candle_exact.iloc[0]
    else:
        # Look for the closest candle at or after first_candle_time
        first_candle_mask = df_sorted['date_dt'] >= first_candle_time
        first_candle_candidates = df_sorted[first_candle_mask]
        
        if len(first_candle_candidates) == 0:
            print(f"No candles found at or after {first_candle_time.strftime('%Y-%m-%d %H:%M:%S')}")
            return False, None, None
        
        # Get the first candle to check (the one closest after first_candle_time)
        first_candle_to_check = first_candle_candidates.iloc[0]
        print(f"Note: Exact candle at {first_candle_time.strftime('%H:%M:%S')} not found, using {first_candle_to_check['date']}")
    
    # Check if first candle is green (close > open)
    is_first_green = first_candle_to_check['close'] > first_candle_to_check['open']
    
    # Create first candle info for logging
    first_candle_info = {
        'color': 'GREEN' if is_first_green else 'RED',
        'date': first_candle_to_check['date'],
        'open': float(first_candle_to_check['open']),
        'high': float(first_candle_to_check['high']),
        'low': float(first_candle_to_check['low']),
        'close': float(first_candle_to_check['close'])
    }
    
    if is_first_green:
        # First candle is green - it's our signal candle
        signal_candle = {
            'high': float(first_candle_to_check['high']),
            'low': float(first_candle_to_check['low']),
            'open': float(first_candle_to_check['open']),
            'close': float(first_candle_to_check['close'])
        }
        print(f"✅ First candle at {first_candle_to_check['date']} is GREEN - Signal candle detected")
        return True, signal_candle, first_candle_info
    
    # First candle is red - wait for next green candle that meets the pattern
    print(f"⚠️ First candle at {first_candle_to_check['date']} is RED - Waiting for green candle pattern")
    
    # Find all candles after the first candle
    first_candle_timestamp = pd.to_datetime(first_candle_to_check['date'])
    candles_after_first = df_sorted[df_sorted['date_dt'] > first_candle_timestamp]
    
    if len(candles_after_first) == 0:
        return False, None, first_candle_info
    
    # Check each subsequent candle for green candle pattern
    for idx in range(len(candles_after_first)):
        current_candle = candles_after_first.iloc[idx]
        
        # Check if current candle is green
        is_current_green = current_candle['close'] > current_candle['open']
        
        if not is_current_green:
            continue  # Skip red candles
        
        # Current candle is green - check pattern conditions
        # We need at least 1 candle before this green candle
        current_candle_timestamp = pd.to_datetime(current_candle['date'])
        candles_before_current = df_sorted[df_sorted['date_dt'] < current_candle_timestamp]
        
        if len(candles_before_current) < 1:
            continue  # Not enough history
        
        # Get previous candle
        prev_candle = candles_before_current.iloc[-1]  # 14:43 candle (previous)
        
        # Check conditions for green candle pattern:
        # At 14:45, we check the green candle (14:44) against the previous candle (14:43)
        # The green candle (14:44) should have both high and low less than previous candle (14:43)
        # This means: 14:44 High < 14:43 High AND 14:44 Low < 14:43 Low
        # (Green candle is completely below the previous candle)
        condition1 = current_candle['high'] < prev_candle['high']
        condition2 = current_candle['low'] < prev_candle['low']
        
        if condition1 and condition2:
            signal_candle = {
                'high': float(current_candle['high']),
                'low': float(current_candle['low']),
                'open': float(current_candle['open']),
                'close': float(current_candle['close'])
            }
            print(f"✅ Green candle pattern found at {current_candle['date']} - Signal candle detected")
            return True, signal_candle, first_candle_info
    
    return False, None, first_candle_info

def calculate_levels(signal_candle, actual_entry_price, t2_percent, t3_percent, t4_percent, sl1_points, sl2_points, sl3_points, sl4_points):
    """
    Calculate all entry, exit, and target levels based on signal candle.

    - entry_trigger is always calculated from SCH.
    - Targets (T1–T4) and SLs (SL1–SL4) are calculated from EP:
        - At signal time: EP = entry_trigger (theoretical entry)
        - After actual entry: EP = actual traded entry price (LTP)
    """
    import math
    
    SCH = signal_candle['high']
    SCL = signal_candle['low']
    
    # Entry trigger = SCH + (√(SCH) × 26.11%)
    entry_trigger = SCH + (math.sqrt(SCH) * 0.2611)
    
    # Initial SL = SCL - (√(SCL) × 26.11%)
    initial_sl = SCL - (math.sqrt(SCL) * 0.2611)
    
    # Decide EP (Entry Price) for target calculations
    # - If actual_entry_price is provided (after real entry), use that
    # - Otherwise (at signal time), use the theoretical entry_trigger
    ep = actual_entry_price if actual_entry_price is not None else entry_trigger
    
    # T1 = EP + 13.06%
    t1 = ep + (ep * 0.1306)
    sl1 = t1 - sl1_points
    
    # T2 = EP + T2Percent%
    t2 = ep + (ep * t2_percent / 100)
    sl2 = t2 - sl2_points
    
    # T3 = EP + T3Percent%
    t3 = ep + (ep * t3_percent / 100)
    sl3 = t3 - sl3_points
    
    # T4 = EP + T4Percent%
    t4 = ep + (ep * t4_percent / 100)
    sl4 = t4 - sl4_points
    
    return {
        'SCH': SCH,
        'SCL': SCL,
        'Entry': entry_trigger,  # Entry trigger price
        'InitialSL': initial_sl,
        'T1': t1,
        'SL1': sl1,
        'T2': t2,
        'SL2': sl2,
        'T3': t3,
        'SL3': sl3,
        'T4': t4,
        'SL4': sl4
    }

def place_buy_order(symbol, quantity, price, product_type="INTRADAY"):
    """Place a buy order (Market order)"""
    try:
        from FyresIntegration import place_order
        response = place_order(symbol=symbol, quantity=quantity, type=2, side=1, price=price, product_type=product_type)
        message = f"[BUY ORDER] {datetime.now()} - Symbol: {symbol}, Qty: {quantity}, Price: {price}, ProductType: {product_type}, Response: {response}"
        print(message)
        write_to_order_logs(message)
        return response
    except Exception as e:
        error_msg = f"[BUY ORDER ERROR] {datetime.now()} - Symbol: {symbol}, Error: {str(e)}"
        print(error_msg)
        write_to_order_logs(error_msg)
        return None

def place_sell_order(symbol, quantity, price, product_type="INTRADAY"):
    """Place a sell order (Market order)"""
    try:
        from FyresIntegration import place_order
        response = place_order(symbol=symbol, quantity=quantity, type=2, side=-1, price=price, product_type=product_type)
        message = f"[SELL ORDER] {datetime.now()} - Symbol: {symbol}, Qty: {quantity}, Price: {price}, ProductType: {product_type}, Response: {response}"
        print(message)
        write_to_order_logs(message)
        return response
    except Exception as e:
        error_msg = f"[SELL ORDER ERROR] {datetime.now()} - Symbol: {symbol}, Error: {str(e)}"
        print(error_msg)
        write_to_order_logs(error_msg)
        return None

def print_trading_status(unique_key, params, positions_state):
    """
    Print compact trading status for a symbol
    """
    try:
        symbol = params.get('Symbol', 'N/A')
        ltp = params.get('FyresLtp')
        ltp_str = f"{ltp:.2f}" if ltp else "N/A"
        
        # Get position state
        pos_state = positions_state.get(unique_key, {})
        
        # Determine status
        if pos_state.get('exited_today'):
            status = "EXITED TODAY"
            status_color = "🔴"
        elif pos_state.get('entry_taken'):
            status = pos_state.get('position_state', 'in_position').upper().replace('_', ' ')
            status_color = "🟢"
        elif pos_state.get('signal_detected'):
            status = "WAITING FOR ENTRY"
            status_color = "🟡"
        else:
            status = "NO SIGNAL"
            status_color = "⚪"
        
        current_timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\n{status_color} {symbol} | LTP: {ltp_str} | {status} | {current_timestamp}")
        
        # Signal Candle Information
        if pos_state.get('signal_detected'):
            sch = pos_state.get('SCH', 0)
            scl = pos_state.get('SCL', 0)
            print(f"   SCH: {sch:.2f} | SCL: {scl:.2f} | Entry: {pos_state.get('Entry', 0):.2f}")
        
        # Entry Information
        entry_price = pos_state.get('Entry', 0)
        entry_taken = pos_state.get('entry_taken', False)
        actual_entry_price = pos_state.get('entry_price', entry_price)
        
        if entry_taken:
            remaining_lots = pos_state.get('remaining_lots', 0)
            pnl = (ltp - actual_entry_price) * remaining_lots if ltp and actual_entry_price else 0
            print(f"   Entry: {actual_entry_price:.2f} ✅ | Lots: {remaining_lots} | P&L: {pnl:+.2f}")
        elif entry_price > 0:
            diff = entry_price - ltp if ltp else 0
            print(f"   Entry: {entry_price:.2f} ⏳ | Distance: {diff:+.2f}")
        
        # Targets & SLs (compact)
        if entry_taken or pos_state.get('signal_detected'):
            t1 = pos_state.get('T1', 0)
            t2 = pos_state.get('T2', 0)
            t3 = pos_state.get('T3', 0)
            t4 = pos_state.get('T4', 0)
            t1_hit = pos_state.get('t1_hit', False)
            t2_hit = pos_state.get('t2_hit', False)
            t3_hit = pos_state.get('t3_hit', False)
            t4_hit = pos_state.get('t4_hit', False)
            
            targets = []
            if t1 > 0: targets.append(f"T1:{t1:.0f}{'✅' if t1_hit else ''}")
            if t2 > 0: targets.append(f"T2:{t2:.0f}{'✅' if t2_hit else ''}")
            if t3 > 0: targets.append(f"T3:{t3:.0f}{'✅' if t3_hit else ''}")
            if t4 > 0: targets.append(f"T4:{t4:.0f}{'✅' if t4_hit else ''}")
            
            if targets:
                print(f"   Targets: {' | '.join(targets)}")
            
            sl = pos_state.get('InitialSL', 0)
            if sl > 0:
                print(f"   SL: {sl:.2f}")
        
        # Trading Hours (compact)
        start_time = params.get('StartTime', 'N/A')
        stop_time = params.get('StopTime', 'N/A')
        current_time = datetime.now().time()
        in_trading_hours = is_time_between(start_time, stop_time, current_time) if start_time != 'N/A' else True
        print(f"   Hours: {start_time}-{stop_time} {'🟢' if in_trading_hours else '🔴'}")
        
    except Exception as e:
        print(f"Error printing status: {str(e)}")

def get_user_settings():
    global result_dict, instrument_id_list, Equity_instrument_id_list, Future_instrument_id_list, FyerSymbolList, positions_state
    import pandas as pd

    # delete_file_contents("OrderLog.txt")

    try:
        csv_path = 'TradeSettings.csv'
        df = pd.read_csv(csv_path)
        df.columns = df.columns.str.strip()

        result_dict = {}
        FyerSymbolList = []

        for index, row in df.iterrows():
            symbol = row['Symbol']
          
            # Create a unique key per row to support duplicate symbols (e.g., CE and PE rows for NIFTY)
            # Using index to ensure uniqueness even if symbols are duplicated
            unique_key = f"{symbol}_{index}"
            
            # Store all columns from CSV into symbol_dict
            symbol_dict = {
                "Symbol": symbol,
                "unique_key": unique_key,
                "Timeframe": int(row['Timeframe']) if pd.notna(row['Timeframe']) else None,
                "EntryLots": int(row['EntryLots']) if pd.notna(row['EntryLots']) else 0,
                "SL1Points": float(row['SL1Points']) if pd.notna(row['SL1Points']) else 0,
                "Sl2Points": float(row['Sl2Points']) if pd.notna(row['Sl2Points']) else 0,
                "Sl3Points": float(row['Sl3Points']) if pd.notna(row['Sl3Points']) else 0,
                "Sl4Points": float(row['Sl4Points']) if pd.notna(row['Sl4Points']) else 0,
                "Tgt1Lots": int(row['Tgt1Lots']) if pd.notna(row['Tgt1Lots']) else 0,
                "Tgt2Lots": int(row['Tgt2Lots']) if pd.notna(row['Tgt2Lots']) else 0,
                "Tgt3Lots": int(row['Tgt3Lots']) if pd.notna(row['Tgt3Lots']) else 0,
                "Tgt4Lots": int(row['Tgt4Lots']) if pd.notna(row['Tgt4Lots']) else 0,
                "T2Percent": float(row['T2Percent']) if pd.notna(row['T2Percent']) else 1.0,
                "T3Percent": float(row['T3Percent']) if pd.notna(row['T3Percent']) else 1.0,
                "T4Percent": float(row['T4Percent']) if pd.notna(row['T4Percent']) else 1.0,
                "StartTime": str(row['StartTime']) if pd.notna(row['StartTime']) else None,
                "StopTime": str(row['StopTime']) if pd.notna(row['StopTime']) else None,
                "ProductType": str(row['ProductType']).lower() if pd.notna(row.get('ProductType', '')) else 'intraday',
                "FyresLtp":None,
            }
            
            # Create FyresSymbol - assuming NSE format, can be modified based on actual requirements
            # If Symbol is already in correct format, use it directly
            if ':' in str(symbol):
                symbol_dict["FyresSymbol"] = symbol
            else:
                # Default to NSE format if not specified
                symbol_dict["FyresSymbol"] = f"NSE:{symbol}"
            
            result_dict[unique_key] = symbol_dict
            FyerSymbolList.append(symbol_dict["FyresSymbol"])
            
        print("result_dict: ", result_dict)
        print("FyerSymbolList: ", FyerSymbolList)
        print("-" * 50)
       

    except Exception as e:
        print("Error happened in fetching symbol", str(e))
        traceback.print_exc()


def UpdateData():
    global result_dict

    for symbol, ltp in shared_data.items(): 
        for key, value in result_dict.items():
            if value.get('FyresSymbol') == symbol:
                value['FyresLtp'] = float(ltp)
                # print(f"Updated {symbol} with LTP: {ltp}")
                break  # Optional: skip if you assume each symbol is unique

def sanitize_symbol_for_filename(symbol):
    """
    Sanitize symbol name to be used as a valid filename.
    Replaces invalid characters with underscores.
    """
    # Replace invalid filename characters with underscore
    invalid_chars = '<>:"/\\|?*'
    sanitized = symbol
    for char in invalid_chars:
        sanitized = sanitized.replace(char, '_')
    # Also replace spaces and colons
    sanitized = sanitized.replace(' ', '_').replace(':', '_')
    return sanitized

def check_signal_for_symbol(unique_key, params, positions_state):
    """
    Phase 1: Check for signal candle pattern for a symbol
    Returns True if signal detected, False otherwise
    """
    try:
        from FyresIntegration import fetchOHLC
        
        symbol = params["FyresSymbol"]
        timeframe = params["Timeframe"]
        start_time = params["StartTime"]
        stop_time = params["StopTime"]
        
        # Check if we're within trading hours
        if not is_time_between(start_time, stop_time):
            return False
        
        # Check if already in position or signal already detected today
        if unique_key in positions_state:
            pos_state = positions_state[unique_key]
            if pos_state.get('signal_detected') or pos_state.get('entry_taken') or pos_state.get('exited_today'):
                return False
        
        # Fetch historical data (fetched at every check)
        check_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n[{symbol}] Fetching historical data at {check_timestamp}")
        df = fetchOHLC(symbol, timeframe)
        
        # Save historical data to CSV file inside ./data folder
        try:
            sanitized_symbol = sanitize_symbol_for_filename(symbol)
            base_dir = os.path.dirname(os.path.abspath(__file__))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            csv_filename = os.path.join(data_dir, f"{sanitized_symbol}.csv")
            # Using overwrite mode to keep latest snapshot of historical data
            df.to_csv(csv_filename, index=False)
            print(f"[{symbol}] Historical data saved to {csv_filename}")
        except Exception as e:
            print(f"[{symbol}] Warning: Failed to save historical data to CSV: {e}")
        
        if len(df) < 3:
            return False
        
        # Filter out the current/forming candle
        # Get the normalized current time (the forming candle's start time)
        now = datetime.now(pytz.timezone('Asia/Kolkata'))
        current_normalized_time = normalize_time_to_timeframe(now, timeframe)
        
        # Filter dataframe to exclude candles at or after the current normalized time
        # Only include completed candles (candles that ended before current time)
        df_completed = df[df['date'] < current_normalized_time].copy()
        
        if len(df_completed) < 2:
            print(f"[{symbol}] Not enough completed candles. Current forming candle: {current_normalized_time.strftime('%Y-%m-%d %H:%M:%S')}")
            return False
        
        # Get last 2 completed candles (before the forming candle)
        last_2_candles = df_completed.tail(2)
        print(f"[{symbol}] Last 2 completed candles data (checked at {check_timestamp}, excluding forming candle at {current_normalized_time.strftime('%H:%M:%S')}):")
        for idx, row in last_2_candles.iterrows():
            date_str = str(row['date'])
            if hasattr(row['date'], 'strftime'):
                date_str = row['date'].strftime('%Y-%m-%d %H:%M:%S')
            print(f"  [{date_str}] O:{row['open']:.2f} H:{row['high']:.2f} L:{row['low']:.2f} C:{row['close']:.2f}")
        
        # Add separator line between each fetch
        print("="*80)
        
        # Check for signal candle using only completed candles
        is_signal, signal_candle, first_candle_info = check_signal_candle(df_completed, start_time, timeframe)
        
        # Log first candle color after StartTime (only once per symbol per day)
        if first_candle_info:
            # Check if we've already logged first candle for this symbol today
            if unique_key not in positions_state:
                positions_state[unique_key] = {}
            
            pos_state = positions_state[unique_key]
            if not pos_state.get('first_candle_logged', False):
                candle_date_str = str(first_candle_info['date'])
                if hasattr(first_candle_info['date'], 'strftime'):
                    candle_date_str = first_candle_info['date'].strftime('%Y-%m-%d %H:%M:%S')
                
                first_candle_log = f"[FIRST CANDLE] {params['Symbol']} - Color: {first_candle_info['color']} | Date: {candle_date_str} | O:{first_candle_info['open']:.2f} H:{first_candle_info['high']:.2f} L:{first_candle_info['low']:.2f} C:{first_candle_info['close']:.2f}"
                print(first_candle_log)
                write_to_order_logs(first_candle_log)
                pos_state['first_candle_logged'] = True
                save_state(positions_state)
        
        if is_signal:
            # Signal detected - OHLC already printed above
            print(f"\n✅ [SIGNAL DETECTED] {symbol} at {datetime.now()}")
            
            # Calculate levels at signal time:
            # - entry_trigger is from SCH
            # - Targets are calculated from EP = entry_trigger (theoretical entry)
            #   (They will be recalculated from actual entry price when entry is taken)
            levels = calculate_levels(
                signal_candle,
                None,  # Use theoretical EP = entry_trigger for initial target calculation
                params["T2Percent"],
                params["T3Percent"],
                params["T4Percent"],
                params["SL1Points"],
                params["Sl2Points"],
                params["Sl3Points"],
                params["Sl4Points"]
            )
            
            # Store signal in state
            positions_state[unique_key] = {
                'signal_detected': True,
                'signal_time': datetime.now().isoformat(),
                'SCH': levels['SCH'],
                'SCL': levels['SCL'],
                'Entry': levels['Entry'],
                'InitialSL': levels['InitialSL'],
                'T1': levels['T1'],
                'SL1': levels['SL1'],
                'T2': levels['T2'],
                'SL2': levels['SL2'],
                'T3': levels['T3'],
                'SL3': levels['SL3'],
                'T4': levels['T4'],
                'SL4': levels['SL4'],
                'entry_taken': False,
                'position_state': 'waiting_entry',
                'remaining_lots': params["EntryLots"],
                't1_hit': False,
                't2_hit': False,
                't3_hit': False,
                't4_hit': False,
                'exited_today': False
            }
            
            # Log comprehensive signal details to OrderLog
            message = f"[SIGNAL DETECTED] {params['Symbol']} at {datetime.now()}"
            write_to_order_logs(message)
            write_to_order_logs(f"  Signal Candle High (SCH): {levels['SCH']:.2f}")
            write_to_order_logs(f"  Signal Candle Low (SCL): {levels['SCL']:.2f}")
            write_to_order_logs(f"  Entry Price: {levels['Entry']:.2f}")
            write_to_order_logs(f"  Initial Stop Loss: {levels['InitialSL']:.2f}")
            write_to_order_logs(f"  Target 1: {levels['T1']:.2f} | SL1: {levels['SL1']:.2f} | Exit Lots: {params['Tgt1Lots']}")
            write_to_order_logs(f"  Target 2: {levels['T2']:.2f} | SL2: {levels['SL2']:.2f} | Exit Lots: {params['Tgt2Lots']}")
            write_to_order_logs(f"  Target 3: {levels['T3']:.2f} | SL3: {levels['SL3']:.2f} | Exit Lots: {params['Tgt3Lots']}")
            write_to_order_logs(f"  Target 4: {levels['T4']:.2f} | SL4: {levels['SL4']:.2f} | Exit Lots: {params['Tgt4Lots']}")
            write_to_order_logs(f"  Entry Lot Size: {params['EntryLots']}")
            write_to_order_logs("")
            
            # Also log last 2 candles OHLC to OrderLog
            write_to_order_logs("Last 2 candles (OHLC):")
            for idx, row in last_2_candles.iterrows():
                date_str = str(row['date'])
                if hasattr(row['date'], 'strftime'):
                    date_str = row['date'].strftime('%Y-%m-%d %H:%M:%S')
                candle_info = f"  Date: {date_str}, Open: {row['open']:.2f}, High: {row['high']:.2f}, Low: {row['low']:.2f}, Close: {row['close']:.2f}, Volume: {int(row['volume']) if pd.notna(row['volume']) else 0}"
                write_to_order_logs(candle_info)
            write_to_order_logs("")
            
            # Print summary to console (duplicate removed)
            print(f"SCH: {levels['SCH']:.2f}, SCL: {levels['SCL']:.2f}, Entry: {levels['Entry']:.2f}")
            save_state(positions_state)
            
            # Print comprehensive status immediately after signal detection
            print_trading_status(unique_key, params, positions_state)
            
            return True
        
        return False
    except Exception as e:
        print(f"Error checking signal for {params.get('Symbol', 'unknown')}: {e}")
        traceback.print_exc()
        return False

def monitor_entry_exit(unique_key, params, positions_state):
    """
    Phase 2: Monitor for entry and exit conditions using LTP
    """
    try:
        if unique_key not in positions_state:
            return
        
        pos_state = positions_state[unique_key]
        
        # Skip if already exited today
        if pos_state.get('exited_today'):
            return
        
        # Skip if no signal detected (but we'll still print status for monitoring)
        # Don't return early - we want to print status even without signal
        if not pos_state.get('signal_detected'):
            # No signal yet - just print status and return (don't process entry/exit)
            # Status printing will be handled in main_strategy loop
            return
        
        # Track last status print time
        current_time = datetime.now(pytz.timezone('Asia/Kolkata'))
        last_status_print = pos_state.get('last_status_print')
        
        # Print status every 30 seconds or on first signal
        should_print_status = False
        if last_status_print is None:
            should_print_status = True
            pos_state['last_status_print'] = current_time.isoformat()
        else:
            if isinstance(last_status_print, str):
                last_status_print = datetime.fromisoformat(last_status_print)
                # Ensure timezone-aware
                if last_status_print.tzinfo is None:
                    last_status_print = pytz.timezone('Asia/Kolkata').localize(last_status_print)
            time_diff = (current_time - last_status_print).total_seconds()
            if time_diff >= 30:  # Print every 30 seconds
                should_print_status = True
                pos_state['last_status_print'] = current_time.isoformat()
        
        if should_print_status:
            print_trading_status(unique_key, params, positions_state)
        
        ltp = params.get('FyresLtp')
        if ltp is None:
            return
        
        start_time = params["StartTime"]
        stop_time = params["StopTime"]
        
        # Check for intraday square-off at StopTime (check this before trading hours check)
        product_type = params.get('ProductType', 'intraday').lower()
        current_time = datetime.now().time()
        
        # Check if current time has reached or passed StopTime
        if stop_time and pos_state.get('entry_taken'):
            try:
                stop_hour, stop_min = map(int, stop_time.split(':'))
                stop_time_obj = dt_time(stop_hour, stop_min)
                
                # If current time >= StopTime and product type is intraday, square off
                if current_time >= stop_time_obj and product_type == 'intraday':
                    if not pos_state.get('squared_off_at_stoptime', False):
                        remaining_lots = pos_state.get('remaining_lots', 0)
                        if remaining_lots > 0:
                            place_sell_order(params["FyresSymbol"], remaining_lots, ltp, product_type)
                            pos_state['exited_today'] = True
                            pos_state['position_state'] = 'squared_off_stoptime'
                            pos_state['squared_off_at_stoptime'] = True
                            message = f"[SQUARE OFF - StopTime] {params['Symbol']} at {ltp:.2f}, Lots: {remaining_lots} (Intraday)"
                            print(message)
                            write_to_order_logs(message)
                            save_state(positions_state)
                            return
            except Exception as e:
                print(f"Error checking StopTime for {params.get('Symbol', 'unknown')}: {e}")
        
        # Check if we're within trading hours
        if not is_time_between(start_time, stop_time):
            return
        
        entry_price = pos_state['Entry']
        position_state = pos_state.get('position_state', 'waiting_entry')
        
        # Entry Logic
        if position_state == 'waiting_entry' and ltp >= entry_price:
            # Take entry
            entry_lots = params["EntryLots"]
            product_type = params.get("ProductType", "intraday")
            response = place_buy_order(params["FyresSymbol"], entry_lots, ltp, product_type)
            
            if response:
                # Recalculate levels with actual entry price
                signal_candle = {'high': pos_state['SCH'], 'low': pos_state['SCL']}
                levels = calculate_levels(
                    signal_candle,
                    ltp,  # Actual entry price
                    params["T2Percent"],
                    params["T3Percent"],
                    params["T4Percent"],
                    params["SL1Points"],
                    params["Sl2Points"],
                    params["Sl3Points"],
                    params["Sl4Points"]
                )
                
                pos_state['entry_taken'] = True
                pos_state['position_state'] = 'in_position'
                pos_state['entry_price'] = ltp
                pos_state['entry_time'] = datetime.now().isoformat()
                pos_state['remaining_lots'] = entry_lots
                pos_state['Entry'] = ltp
                pos_state['InitialSL'] = levels['InitialSL']
                pos_state['T1'] = levels['T1']
                pos_state['SL1'] = levels['SL1']
                pos_state['T2'] = levels['T2']
                pos_state['SL2'] = levels['SL2']
                pos_state['T3'] = levels['T3']
                pos_state['SL3'] = levels['SL3']
                pos_state['T4'] = levels['T4']
                pos_state['SL4'] = levels['SL4']
                
                # Log entry taken to OrderLog
                message = f"[ENTRY PRICE REACHED] {params['Symbol']} at {datetime.now()}"
                write_to_order_logs(message)
                write_to_order_logs(f"  Entry Price: {ltp:.2f}")
                write_to_order_logs(f"  Taking BUY position with {entry_lots} lots")
                write_to_order_logs("")
                
                # Also print to console
                print(f"[ENTRY TAKEN] {params['Symbol']} at {ltp:.2f}, Lots: {entry_lots}, T1: {levels['T1']:.2f}, T2: {levels['T2']:.2f}, T3: {levels['T3']:.2f}, T4: {levels['T4']:.2f}")
                save_state(positions_state)
                
                # Print comprehensive status immediately after entry
                print_trading_status(unique_key, params, positions_state)
        
        # Exit Logic (only if entry is taken)
        if not pos_state.get('entry_taken'):
            return
        
        # Get product_type from params for order placement
        product_type = params.get("ProductType", "intraday")
        
        initial_sl = pos_state['InitialSL']
        t1 = pos_state['T1']
        sl1 = pos_state['SL1']
        t2 = pos_state['T2']
        sl2 = pos_state['SL2']
        t3 = pos_state['T3']
        sl3 = pos_state['SL3']
        t4 = pos_state['T4']
        sl4 = pos_state['SL4']
        remaining_lots = pos_state.get('remaining_lots', 0)
        
        # State machine for exits
        if position_state == 'in_position':
            # Check Initial SL
            if ltp <= initial_sl:
                # Exit all remaining lots
                if remaining_lots > 0:
                    place_sell_order(params["FyresSymbol"], remaining_lots, ltp, product_type)
                    pos_state['exited_today'] = True
                    pos_state['position_state'] = 'exited_sl'
                    message = f"[EXIT - Initial SL] {params['Symbol']} at {ltp:.2f}, Lots: {remaining_lots}. All positions closed - no more trades today. Fresh pattern check next day."
                    print(message)
                    write_to_order_logs(message)
                    save_state(positions_state)
                return  # Exit monitoring for this symbol today
            
            # Check T1
            if ltp >= t1:
                tgt1_lots = params["Tgt1Lots"]
                if tgt1_lots > 0 and remaining_lots >= tgt1_lots:
                    place_sell_order(params["FyresSymbol"], tgt1_lots, ltp, product_type)
                    pos_state['remaining_lots'] -= tgt1_lots
                    pos_state['t1_hit'] = True
                    pos_state['position_state'] = 't1_hit'
                    message = f"[T1 HIT] {params['Symbol']} at {ltp:.2f}, Exited: {tgt1_lots} lots, Remaining: {pos_state['remaining_lots']}"
                    print(message)
                    write_to_order_logs(message)
                    save_state(positions_state)

        elif position_state == 't1_hit':
            # Check SL1 or T2
            if ltp <= sl1:
                # Exit all remaining lots
                if remaining_lots > 0:
                    place_sell_order(params["FyresSymbol"], remaining_lots, ltp, product_type)
                    pos_state['exited_today'] = True
                    pos_state['position_state'] = 'exited_sl1'
                    message = f"[EXIT - SL1] {params['Symbol']} at {ltp:.2f}, Lots: {remaining_lots}. All positions closed - no more trades today. Fresh pattern check next day."
                    print(message)
                    write_to_order_logs(message)
                    save_state(positions_state)
                    return  # Exit monitoring for this symbol today
            elif ltp >= t2:
                tgt2_lots = params["Tgt2Lots"]
                if tgt2_lots > 0 and remaining_lots >= tgt2_lots:
                    place_sell_order(params["FyresSymbol"], tgt2_lots, ltp, product_type)
                    pos_state['remaining_lots'] -= tgt2_lots
                    pos_state['t2_hit'] = True
                    pos_state['position_state'] = 't2_hit'
                    message = f"[T2 HIT] {params['Symbol']} at {ltp:.2f}, Exited: {tgt2_lots} lots, Remaining: {pos_state['remaining_lots']}"
                    print(message)
                    write_to_order_logs(message)
                    save_state(positions_state)
        
        elif position_state == 't2_hit':
            # Check SL2 or T3
            if ltp <= sl2:
                # Exit all remaining lots
                if remaining_lots > 0:
                    place_sell_order(params["FyresSymbol"], remaining_lots, ltp, product_type)
                    pos_state['exited_today'] = True
                    pos_state['position_state'] = 'exited_sl2'
                    message = f"[EXIT - SL2] {params['Symbol']} at {ltp:.2f}, Lots: {remaining_lots}. All positions closed - no more trades today. Fresh pattern check next day."
                    print(message)
                    write_to_order_logs(message)
                    save_state(positions_state)
                    return  # Exit monitoring for this symbol today
            elif ltp >= t3:
                tgt3_lots = params["Tgt3Lots"]
                if tgt3_lots > 0 and remaining_lots >= tgt3_lots:
                    place_sell_order(params["FyresSymbol"], tgt3_lots, ltp, product_type)
                    pos_state['remaining_lots'] -= tgt3_lots
                    pos_state['t3_hit'] = True
                    pos_state['position_state'] = 't3_hit'
                    message = f"[T3 HIT] {params['Symbol']} at {ltp:.2f}, Exited: {tgt3_lots} lots, Remaining: {pos_state['remaining_lots']}"
                    print(message)
                    write_to_order_logs(message)
                    save_state(positions_state)
        
        elif position_state == 't3_hit':
            # Check SL3 or T4
            if ltp <= sl3:
                # Exit all remaining lots
                if remaining_lots > 0:
                    place_sell_order(params["FyresSymbol"], remaining_lots, ltp, product_type)
                    pos_state['exited_today'] = True
                    pos_state['position_state'] = 'exited_sl3'
                    message = f"[EXIT - SL3] {params['Symbol']} at {ltp:.2f}, Lots: {remaining_lots}. All positions closed - no more trades today. Fresh pattern check next day."
                    print(message)
                    write_to_order_logs(message)
                    save_state(positions_state)
                    return  # Exit monitoring for this symbol today
            elif ltp >= t4:
                # T4 hit - exit ALL remaining lots, close all positions for the day
                if remaining_lots > 0:
                    place_sell_order(params["FyresSymbol"], remaining_lots, ltp, product_type)
                    pos_state['remaining_lots'] = 0
                    pos_state['t4_hit'] = True
                    pos_state['position_state'] = 't4_hit'
                    # After T4 hit, mark as exited_today - no more trades for present day
                    pos_state['exited_today'] = True
                    message = f"[T4 HIT] {params['Symbol']} at {ltp:.2f}, Exited ALL {remaining_lots} lots. All positions closed - no more trades today. Fresh pattern check next day."
                    print(message)
                    write_to_order_logs(message)
                    save_state(positions_state)
                    return  # Exit monitoring for this symbol today
        
        # Note: t4_hit state should not be reached since we exit all lots and return above
        # This is kept as a safety check only
        elif position_state == 't4_hit':
            # This should not happen since all lots are exited when T4 is hit
            # But kept as safety check - exit any remaining lots if somehow reached
            if remaining_lots > 0:
                place_sell_order(params["FyresSymbol"], remaining_lots, ltp, product_type)
                pos_state['exited_today'] = True
                pos_state['position_state'] = 'exited_sl4'
                message = f"[EXIT - SL4 Safety] {params['Symbol']} at {ltp:.2f}, Lots: {remaining_lots}. All positions closed - no more trades today. Fresh pattern check next day."
                print(message)
                write_to_order_logs(message)
                save_state(positions_state)
                return  # Exit monitoring for this symbol today
    
    except Exception as e:
        print(f"Error monitoring entry/exit for {params.get('Symbol', 'unknown')}: {e}")
        traceback.print_exc()

def main_strategy():
    """
    Main strategy function that handles both signal detection and entry/exit monitoring
    """
    try:
        global result_dict, positions_state
        
        # Update LTP data
        UpdateData()
        
        now = datetime.now(pytz.timezone('Asia/Kolkata'))
        
        # Phase 1: Check for signals (timeframe-based, per symbol)
        for unique_key, params in result_dict.items():
            timeframe = params.get("Timeframe")
            if timeframe is None:
                continue
            
            # Get or initialize next_check_time for this symbol
            if unique_key not in positions_state:
                positions_state[unique_key] = {}
            
            pos_state = positions_state[unique_key]
            next_check_time = pos_state.get('next_check_time')
            
            # Initialize next_check_time if not set
            if next_check_time is None:
                # Set first check time to StartTime + 1 second (e.g., 9:25:01)
                start_time_str = params.get("StartTime")
                if start_time_str:
                    try:
                        start_hour, start_min = map(int, start_time_str.split(':'))
                        # Create datetime for today at StartTime + 1 second
                        today = now.date()
                        first_check_time = pytz.timezone('Asia/Kolkata').localize(datetime.combine(today, dt_time(start_hour, start_min, 1)))
                        # If StartTime has already passed today, set to next timeframe interval
                        if now >= first_check_time:
                            normalized_time = normalize_time_to_timeframe(now, timeframe)
                            next_check_time = normalized_time + timedelta(minutes=timeframe)
                        else:
                            next_check_time = first_check_time
                    except Exception as e:
                        print(f"Error parsing StartTime for {params.get('Symbol', 'unknown')}: {e}")
                        # Fallback to normalized time logic
                        normalized_time = normalize_time_to_timeframe(now, timeframe)
                        next_check_time = normalized_time + timedelta(minutes=timeframe)
                else:
                    # No StartTime specified, use normalized time logic
                    normalized_time = normalize_time_to_timeframe(now, timeframe)
                    next_check_time = normalized_time + timedelta(minutes=timeframe)
                
                pos_state['next_check_time'] = next_check_time.isoformat()
                save_state(positions_state)
            
            # Convert string back to datetime
            if isinstance(next_check_time, str):
                next_check_time = datetime.fromisoformat(next_check_time)
                # Ensure timezone-aware (in case it was saved as naive)
                if next_check_time.tzinfo is None:
                    next_check_time = pytz.timezone('Asia/Kolkata').localize(next_check_time)
            
            # Check if it's time to fetch historical data
            if now >= next_check_time:
                # Check for signal
                signal_detected = check_signal_for_symbol(unique_key, params, positions_state)
                
                # Update next check time
                normalized_time = normalize_time_to_timeframe(now, timeframe)
                next_check_time = normalized_time + timedelta(minutes=timeframe)
                pos_state['next_check_time'] = next_check_time.isoformat()
                save_state(positions_state)
        
        # Phase 2: Monitor entry/exit for symbols with signals (every second)
        # This includes carry-forward positions from previous day
        for unique_key, params in result_dict.items():
            monitor_entry_exit(unique_key, params, positions_state)
        
        # Print status for all symbols periodically
        # For symbols with signals/positions: print every 30 seconds
        # For symbols without signals: print every 60 seconds to show they're being monitored
        for unique_key, params in result_dict.items():
            # Ensure position state exists for this symbol
            if unique_key not in positions_state:
                positions_state[unique_key] = {}
            
            pos_state = positions_state[unique_key]
            current_time = datetime.now(pytz.timezone('Asia/Kolkata'))
            last_status_print = pos_state.get('last_status_print')
            
            # Determine print interval based on whether signal/entry exists
            has_signal_or_entry = pos_state.get('signal_detected') or pos_state.get('entry_taken')
            print_interval = 30 if has_signal_or_entry else 60  # 30s for active, 60s for monitoring
            
            should_print = False
            if last_status_print is None:
                # First time - always print
                should_print = True
                pos_state['last_status_print'] = current_time.isoformat()
            else:
                if isinstance(last_status_print, str):
                    last_status_print = datetime.fromisoformat(last_status_print)
                    # Ensure timezone-aware
                    if last_status_print.tzinfo is None:
                        last_status_print = pytz.timezone('Asia/Kolkata').localize(last_status_print)
                time_diff = (current_time - last_status_print).total_seconds()
                if time_diff >= print_interval:
                    should_print = True
                    pos_state['last_status_print'] = current_time.isoformat()
            
            if should_print:
                print_trading_status(unique_key, params, positions_state)
                save_state(positions_state)
            
    except Exception as e:
        print("Error in main strategy:", str(e))
        traceback.print_exc()



if __name__ == "__main__":
    # # Initialize settings and credentials
    #   # <-- Add this line
    credentials_dict_fyers = get_api_credentials_Fyers()
    redirect_uri = credentials_dict_fyers.get('redirect_uri')
    client_id = credentials_dict_fyers.get('client_id')
    secret_key = credentials_dict_fyers.get('secret_key')
    grant_type = credentials_dict_fyers.get('grant_type')
    response_type = credentials_dict_fyers.get('response_type')
    state = credentials_dict_fyers.get('state')
    TOTP_KEY = credentials_dict_fyers.get('totpkey')
    FY_ID = credentials_dict_fyers.get('FY_ID')
    PIN = credentials_dict_fyers.get('PIN')
        # Automated login and initialization steps
    automated_login(client_id=client_id, redirect_uri=redirect_uri, secret_key=secret_key, FY_ID=FY_ID,
                                        PIN=PIN, TOTP_KEY=TOTP_KEY)
    get_user_settings()
    
    # Log startup information to console and OrderLog
    startup_time = datetime.now()
    print(f"\n{'='*80}")
    print(f"[PROJECT START] Trading Strategy Started at {startup_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[STARTUP] Strategy initialized at {startup_time}")
    print(f"[STARTUP] Loaded {len(result_dict)} symbol(s) from TradeSettings.csv")
    for unique_key, params in result_dict.items():
        product_type = params.get('ProductType', 'intraday')
        timeframe = params.get('Timeframe', 'N/A')
        start_time = params.get('StartTime', 'N/A')
        stop_time = params.get('StopTime', 'N/A')
        print(f"  - {params['Symbol']} (ProductType: {product_type}, Timeframe: {timeframe} min, StartTime: {start_time}, StopTime: {stop_time})")
    print(f"{'='*80}\n")
    
    write_to_order_logs(f"\n{'='*80}")
    write_to_order_logs(f"[PROJECT START] Trading Strategy Started at {startup_time.strftime('%Y-%m-%d %H:%M:%S')}")
    write_to_order_logs(f"[STARTUP] Strategy initialized at {startup_time}")
    write_to_order_logs(f"[STARTUP] Loaded {len(result_dict)} symbol(s) from TradeSettings.csv")
    for unique_key, params in result_dict.items():
        product_type = params.get('ProductType', 'intraday')
        timeframe = params.get('Timeframe', 'N/A')
        start_time = params.get('StartTime', 'N/A')
        stop_time = params.get('StopTime', 'N/A')
        write_to_order_logs(f"  - {params['Symbol']} (ProductType: {product_type}, Timeframe: {timeframe} min, StartTime: {start_time}, StopTime: {stop_time})")
    write_to_order_logs(f"{'='*80}\n")
    
    # Load state - this is positional strategy, so we need to carry forward positions
    # Make positions_state global so it persists across main_strategy calls
    global positions_state
    loaded_state, state_date = load_state()
    positions_state = loaded_state
    today = datetime.now().date().isoformat()
    
    # Handle daily reset logic based on ProductType
    if state_date != today and state_date is not None:
        print(f"\n[STATE] Previous day detected: {state_date} | Today: {today}")
        print("[STATE] Processing carry-forward positions...")
        
        for key in list(positions_state.keys()):
            pos_state = positions_state[key]
            
            # Get ProductType for this symbol (check if key exists in result_dict)
            product_type = 'intraday'  # Default
            if key in result_dict:
                product_type = result_dict[key].get('ProductType', 'intraday').lower()
            
            # If position was exited yesterday
            if pos_state.get('exited_today'):
                # For intraday: clear it for fresh pattern check today
                # For positional: also clear (position was exited, so start fresh)
                symbol_name = pos_state.get('Symbol', key)
                print(f"[STATE] Clearing exited position for {symbol_name} (ProductType: {product_type}) - will check for fresh pattern")
                write_to_order_logs(f"[STATE] Clearing exited position for {symbol_name} (ProductType: {product_type}) - will check for fresh pattern")
                positions_state[key] = {}  # Clear state for fresh pattern check
            elif pos_state.get('entry_taken'):
                # Position is still open
                symbol_name = pos_state.get('Symbol', key)
                if product_type == 'positional':
                    # Positional: continue monitoring it
                    print(f"[STATE] Carrying forward OPEN POSITIONAL position for {symbol_name}")
                    print(f"        Entry Price: {pos_state.get('entry_price', 'N/A')}")
                    print(f"        Remaining Lots: {pos_state.get('remaining_lots', 0)}")
                    print(f"        Position State: {pos_state.get('position_state', 'N/A')}")
                    write_to_order_logs(f"[STATE] Carrying forward OPEN POSITIONAL position for {symbol_name}")
                    write_to_order_logs(f"  Entry Price: {pos_state.get('entry_price', 'N/A')}")
                    write_to_order_logs(f"  Remaining Lots: {pos_state.get('remaining_lots', 0)}")
                    write_to_order_logs(f"  Position State: {pos_state.get('position_state', 'N/A')}")
                    # Reset exited_today flag for new day
                    pos_state['exited_today'] = False
                else:
                    # Intraday: should have been squared off at StopTime, but if not, clear it
                    print(f"[STATE] Clearing intraday position for {symbol_name} - should have been squared off at StopTime")
                    write_to_order_logs(f"[STATE] Clearing intraday position for {symbol_name} - should have been squared off at StopTime")
                    positions_state[key] = {}  # Clear state for fresh pattern check
            elif pos_state.get('signal_detected') and not pos_state.get('entry_taken'):
                # Signal detected but entry not taken (for ANY product type)
                # New day should start FRESH and look for a new pattern
                symbol_name = pos_state.get('Symbol', key)
                print(f"[STATE] Clearing pending SIGNAL (no entry taken) for {symbol_name} (ProductType: {product_type}) - will check for fresh pattern today")
                write_to_order_logs(f"[STATE] Clearing pending SIGNAL (no entry taken) for {symbol_name} (ProductType: {product_type}) - will check for fresh pattern today")
                positions_state[key] = {}  # Clear state for fresh pattern check
            else:
                # Empty or invalid state - clear it
                positions_state[key] = {}
        
        # Save updated state
        save_state(positions_state)
        print("[STATE] State updated for new trading day\n")
        write_to_order_logs("[STATE] State updated for new trading day\n")
    elif state_date == today:
        print(f"[STATE] Loading state from today: {today}")
        write_to_order_logs(f"[STATE] Loading state from today: {today}")
        open_positions = [k for k, v in positions_state.items() if v.get('entry_taken')]
        if open_positions:
            print(f"[STATE] Found {len(open_positions)} open position(s) to monitor")
            write_to_order_logs(f"[STATE] Found {len(open_positions)} open position(s) to monitor")
            for pos_key in open_positions:
                pos = positions_state[pos_key]
                symbol_name = pos.get('Symbol', pos_key)
                write_to_order_logs(f"  - {symbol_name}: Entry Price: {pos.get('entry_price', 'N/A')}, Remaining Lots: {pos.get('remaining_lots', 0)}")
    else:
        print("[STATE] No previous state found - starting fresh")
        print("[STATE] All symbols will check for fresh green candle patterns")
        print("[STATE] No carry-forward positions - clean start")
        write_to_order_logs("[STATE] No previous state found - starting fresh")
        write_to_order_logs("[STATE] All symbols will check for fresh green candle patterns")
        write_to_order_logs("[STATE] No carry-forward positions - clean start")

    # Initialize Market Data API
    fyres_websocket(FyerSymbolList)
    time.sleep(5)
    
    print(f"[STARTUP] Strategy initialized at {datetime.now()}")
    print(f"[STARTUP] Monitoring {len(result_dict)} symbols")
    
    while True:
        try:
            main_strategy()
            time.sleep(1)
        except KeyboardInterrupt:
            print("\n[SHUTDOWN] Strategy stopped by user")
            break
        except Exception as e:
            print(f"[ERROR] Unexpected error in main loop: {e}")
            traceback.print_exc()
            time.sleep(1)
         
    
