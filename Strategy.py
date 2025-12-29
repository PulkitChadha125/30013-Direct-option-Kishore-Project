expierdate="2026-12-29"
message="Project validity expiered please contact admin"


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

# State.json removed - intraday mode, fresh start each day
# No need to save/load state since we start fresh every day

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
            
            # Skip empty rows
            if pd.isna(symbol) or str(symbol).strip() == '':
                continue
          
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
                "T1Percent": float(row['T1Percent']) if pd.notna(row['T1Percent']) else 1.0,
                "T2Percent": float(row['T2Percent']) if pd.notna(row['T2Percent']) else 1.0,
                "T3Percent": float(row['T3Percent']) if pd.notna(row['T3Percent']) else 1.0,
                "T4Percent": float(row['T4Percent']) if pd.notna(row['T4Percent']) else 1.0,
                "StartTime": str(row['StartTime']) if pd.notna(row['StartTime']) else None,
                "StopTime": str(row['StopTime']) if pd.notna(row['StopTime']) else None,
                "Market": str(row['Market']) if pd.notna(row.get('Market', '')) else None,
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

def calculate_entry_price(signal_candle_value, direction, market_type):
    """
    Calculate entry price based on signal candle, direction, and market type.
    
    Args:
        signal_candle_value: SCH value (high for BUY, low for SELL)
        direction: 'BUY' or 'SELL'
        market_type: 'IO' (Index Options) or 'UL' (Underlying/Stock/Futures/Commodity)
    
    Returns:
        float: Entry price
    """
    import math
    
    if market_type.upper() == 'IO':
        # Index Options: Use square root
        if direction.upper() == 'BUY':
            entry = signal_candle_value + (math.sqrt(signal_candle_value) * 0.2611)
        else:  # SELL
            entry = signal_candle_value - (math.sqrt(signal_candle_value) * 0.2611)
    else:  # UL
        # Underlying/Stock/Futures/Commodity: Use cube root
        if direction.upper() == 'BUY':
            entry = signal_candle_value + (signal_candle_value ** (1/3) * 0.2611)
        else:  # SELL
            entry = signal_candle_value - (signal_candle_value ** (1/3) * 0.2611)
    
    return entry

def calculate_initial_sl(signal_candle_low, signal_candle_high, direction, market_type):
    """
    Calculate initial stop loss based on signal candle and market type.
    
    Args:
        signal_candle_low: SCL (signal candle low)
        signal_candle_high: SCH (signal candle high)
        direction: 'BUY' or 'SELL'
        market_type: 'IO' (Index Options) or 'UL' (Underlying)
    
    Returns:
        float: Initial stop loss
    """
    import math
    
    if market_type.upper() == 'IO':
        # Index Options: Use square root
        if direction.upper() == 'BUY':
            initial_sl = signal_candle_low - (math.sqrt(signal_candle_low) * 0.2611)
        else:  # SELL
            initial_sl = signal_candle_high + (math.sqrt(signal_candle_high) * 0.2611)
    else:  # UL
        # Underlying: Use cube root
        if direction.upper() == 'BUY':
            initial_sl = signal_candle_low - (signal_candle_low ** (1/3) * 0.2611)
        else:  # SELL
            initial_sl = signal_candle_high + (signal_candle_high ** (1/3) * 0.2611)
    
    return initial_sl

def calculate_levels(entry_price, direction, t1_percent, t2_percent, t3_percent, t4_percent, 
                     sl1_points, sl2_points, sl3_points, sl4_points):
    """
    Calculate all target and stop loss levels based on entry price and direction.
    
    Args:
        entry_price: Entry price (EP)
        direction: 'BUY' or 'SELL'
        t1_percent, t2_percent, t3_percent, t4_percent: Target percentages
        sl1_points, sl2_points, sl3_points, sl4_points: Stop loss points
    
    Returns:
        dict: Dictionary containing all targets and stop losses
    """
    if direction.upper() == 'BUY':
        # BUY: Targets above entry, SLs below
        t1 = entry_price + (entry_price * t1_percent / 100)
        t2 = entry_price + (entry_price * t2_percent / 100)
        t3 = entry_price + (entry_price * t3_percent / 100)
        t4 = entry_price + (entry_price * t4_percent / 100)
        
        sl1 = entry_price - sl1_points
        sl2 = t1 - sl2_points
        sl3 = t2 - sl3_points
        sl4 = t3 - sl4_points
    else:  # SELL
        # SELL: Targets below entry, SLs above
        t1 = entry_price - (entry_price * t1_percent / 100)
        t2 = entry_price - (entry_price * t2_percent / 100)
        t3 = entry_price - (entry_price * t3_percent / 100)
        t4 = entry_price - (entry_price * t4_percent / 100)
        
        sl1 = entry_price + sl1_points
        sl2 = t1 + sl2_points
        sl3 = t2 + sl3_points
        sl4 = t3 + sl4_points
    
    return {
        'T1': t1,
        'T2': t2,
        'T3': t3,
        'T4': t4,
        'SL1': sl1,
        'SL2': sl2,
        'SL3': sl3,
        'SL4': sl4
    }

def update_candle_data_for_dashboard(unique_key, params, positions_state):
    """
    Fetch and store the last 2 completed candles for dashboard display.
    This runs for all symbols regardless of StartTime to keep dashboard updated.
    """
    try:
        from FyresIntegration import fetchOHLC
        
        symbol = params["FyresSymbol"]
        timeframe = params["Timeframe"]
        
        # Initialize position state if needed
        if unique_key not in positions_state:
            positions_state[unique_key] = {}
        pos_state = positions_state[unique_key]
        
        # Fetch historical data
        df = fetchOHLC(symbol, timeframe)
        
        if len(df) < 2:
            return
        
        # Filter out the current/forming candle
        now = datetime.now(pytz.timezone('Asia/Kolkata'))
        current_normalized_time = normalize_time_to_timeframe(now, timeframe)
        
        # Filter dataframe to exclude candles at or after the current normalized time
        df_completed = df[df['date'] < current_normalized_time].copy()
        
        if len(df_completed) < 2:
            return
        
        # Get last 2 completed candles
        last_2_candles = df_completed.tail(2)
        
        if len(last_2_candles) < 2:
            return
        
        # Get the two candles: current (most recent) and previous
        current_candle = last_2_candles.iloc[-1]  # Most recent completed candle
        prev_candle = last_2_candles.iloc[-2]     # Previous candle
        
        # Store last 2 candles info for dashboard
        def get_candle_info(candle_row):
            date_str = str(candle_row['date'])
            if hasattr(candle_row['date'], 'strftime'):
                date_str = candle_row['date'].strftime('%Y-%m-%d %H:%M:%S')
            color = 'GREEN' if candle_row['close'] > candle_row['open'] else 'RED'
            return {
                'date': candle_row['date'],
                'date_str': date_str,
                'color': color,
                'open': float(candle_row['open']),
                'high': float(candle_row['high']),
                'low': float(candle_row['low']),
                'close': float(candle_row['close'])
            }
        
        pos_state['last_candle_1'] = get_candle_info(current_candle)  # Most recent
        pos_state['last_candle_2'] = get_candle_info(prev_candle)      # Previous
        
        # Log FIRST CANDLE if not logged yet (for dashboard updates)
        if not pos_state.get('first_candle_logged', False):
            candle_color = 'GREEN' if current_candle['close'] > current_candle['open'] else 'RED'
            candle_date_str = str(current_candle['date'])
            if hasattr(current_candle['date'], 'strftime'):
                candle_date_str = current_candle['date'].strftime('%Y-%m-%d %H:%M:%S')
            
            first_candle_log = f"[FIRST CANDLE] {params.get('Symbol', 'unknown')} - Color: {candle_color} | Date: {candle_date_str} | O:{current_candle['open']:.2f} H:{current_candle['high']:.2f} L:{current_candle['low']:.2f} C:{current_candle['close']:.2f}"
            print(first_candle_log)
            write_to_order_logs(first_candle_log)
            pos_state['first_candle_logged'] = True
        
    except Exception as e:
        # Log error but don't spam - only log once per symbol
        if not pos_state.get('candle_update_error_logged', False):
            print(f"[CANDLE UPDATE ERROR] {params.get('Symbol', 'unknown')}: {str(e)}")
            pos_state['candle_update_error_logged'] = True

def check_signal_for_symbol(unique_key, params, positions_state):
    """
    Check for signal candle pattern for a symbol by examining the previous two completed candles.
    Returns True if signal detected, False otherwise.
    """
    try:
        from FyresIntegration import fetchOHLC
        
        symbol = params["FyresSymbol"]
        timeframe = params["Timeframe"]
        start_time = params["StartTime"]
        stop_time = params["StopTime"]
        
        # Initialize position state
        if unique_key not in positions_state:
            positions_state[unique_key] = {}
        pos_state = positions_state[unique_key]
        
        # Check if we're within trading hours
        if not is_time_between(start_time, stop_time):
            return False
        
        # Check if already in position or signal already detected today (one trade per day)
        if pos_state.get('signal_detected') or pos_state.get('entry_taken') or pos_state.get('exited_today'):
            return False
        
        # Fetch historical data
        check_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n[{symbol}] Fetching historical data at {check_timestamp}")
        df = fetchOHLC(symbol, timeframe)
        
        # Save historical data to CSV file inside ./data folder
        # Use the actual symbol name from params (not FyresSymbol which has NSE: prefix)
        try:
            actual_symbol = params.get('Symbol', symbol)
            # Remove exchange prefix if present (e.g., "NSE:SYMBOL" -> "SYMBOL")
            if ':' in actual_symbol:
                actual_symbol = actual_symbol.split(':')[-1]
            
            base_dir = os.path.dirname(os.path.abspath(__file__))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            csv_filename = os.path.join(data_dir, f"{actual_symbol}.csv")
            # Using overwrite mode to keep latest snapshot of historical data
            df.to_csv(csv_filename, index=False)
            print(f"[{symbol}] Historical data saved to {csv_filename}")
        except Exception as e:
            print(f"[{symbol}] Warning: Failed to save historical data to CSV: {e}")
        
        if len(df) < 2:
            print(f"[{symbol}] Not enough candles in historical data")
            return False
        
        # Filter out the current/forming candle
        # Get the normalized current time (the forming candle's start time)
        # Example: At 9:30, the forming candle is 9:30, so we check 9:25 and 9:20 (last 2 completed)
        now = datetime.now(pytz.timezone('Asia/Kolkata'))
        current_normalized_time = normalize_time_to_timeframe(now, timeframe)
        
        # Filter dataframe to exclude candles at or after the current normalized time
        # Only include completed candles (candles that ended before current time)
        df_completed = df[df['date'] < current_normalized_time].copy()
        
        if len(df_completed) < 2:
            print(f"[{symbol}] Not enough completed candles. Current forming candle: {current_normalized_time.strftime('%Y-%m-%d %H:%M:%S')}")
            return False
        
        # Get last 2 completed candles (before the forming candle)
        # At 9:30, this will be 9:25 (most recent) and 9:20 (previous)
        last_2_candles = df_completed.tail(2)
        
        if len(last_2_candles) < 2:
            print(f"[{symbol}] Not enough candles to check pattern")
            return False
        
        # Get the two candles: current (most recent) and previous
        current_candle = last_2_candles.iloc[-1]  # Most recent completed candle (e.g., 9:25)
        prev_candle = last_2_candles.iloc[-2]     # Previous candle (e.g., 9:20)
        
        # Store last 2 candles info for dashboard (always store, even if no signal)
        def get_candle_info(candle_row):
            date_str = str(candle_row['date'])
            if hasattr(candle_row['date'], 'strftime'):
                date_str = candle_row['date'].strftime('%Y-%m-%d %H:%M:%S')
            color = 'GREEN' if candle_row['close'] > candle_row['open'] else 'RED'
            return {
                'date': candle_row['date'],
                'date_str': date_str,
                'color': color,
                'open': float(candle_row['open']),
                'high': float(candle_row['high']),
                'low': float(candle_row['low']),
                'close': float(candle_row['close'])
            }
        
        pos_state['last_candle_1'] = get_candle_info(current_candle)  # Most recent (e.g., 9:25)
        pos_state['last_candle_2'] = get_candle_info(prev_candle)      # Previous (e.g., 9:20)
        
        # Log FIRST CANDLE (current candle being checked) - only once per symbol per day
        if not pos_state.get('first_candle_logged', False):
            # Determine candle color
            candle_color = 'GREEN' if current_candle['close'] > current_candle['open'] else 'RED'
            candle_date_str = str(current_candle['date'])
            if hasattr(current_candle['date'], 'strftime'):
                candle_date_str = current_candle['date'].strftime('%Y-%m-%d %H:%M:%S')
            
            first_candle_log = f"[FIRST CANDLE] {params['Symbol']} - Color: {candle_color} | Date: {candle_date_str} | O:{current_candle['open']:.2f} H:{current_candle['high']:.2f} L:{current_candle['low']:.2f} C:{current_candle['close']:.2f}"
            print(first_candle_log)
            write_to_order_logs(first_candle_log)
            pos_state['first_candle_logged'] = True
        
        # Print the two candles being checked (OHLC)
        print(f"[{symbol}] Checking previous 2 completed candles (checked at {check_timestamp}, excluding forming candle at {current_normalized_time.strftime('%H:%M:%S')}):")
        for idx, row in last_2_candles.iterrows():
            date_str = str(row['date'])
            if hasattr(row['date'], 'strftime'):
                date_str = row['date'].strftime('%Y-%m-%d %H:%M:%S')
            print(f"  [{date_str}] O:{row['open']:.2f} H:{row['high']:.2f} L:{row['low']:.2f} C:{row['close']:.2f}")
        
        # Add separator line
        print("="*80)
        
        # Check for BUY signal pattern
        # Current candle (9:25) should be GREEN (close > open)
        # Current candle high < previous candle high
        # Current candle low < previous candle low
        is_current_green = current_candle['close'] > current_candle['open']
        buy_condition1 = current_candle['high'] < prev_candle['high']
        buy_condition2 = current_candle['low'] < prev_candle['low']
        
        # Check for SELL signal pattern
        # Current candle (9:25) should be RED (close < open)
        # Current candle high > previous candle high
        # Current candle low > previous candle low
        is_current_red = current_candle['close'] < current_candle['open']
        sell_condition1 = current_candle['high'] > prev_candle['high']
        sell_condition2 = current_candle['low'] > prev_candle['low']
        
        direction = None
        signal_candle_value = None
        signal_candle_data = None
        
        # Check BUY signal
        if is_current_green and buy_condition1 and buy_condition2:
            direction = 'BUY'
            signal_candle_value = float(current_candle['high'])  # SCH = signal candle high
            signal_candle_data = {
                'high': float(current_candle['high']),
                'low': float(current_candle['low']),
                'open': float(current_candle['open']),
                'close': float(current_candle['close']),
                'date': current_candle['date']
            }
            print(f"✅ [BUY SIGNAL DETECTED] {symbol} at {check_timestamp}")
            print(f"   Signal Candle: {current_candle['date']} | High: {signal_candle_value:.2f}")
        
        # Check SELL signal
        elif is_current_red and sell_condition1 and sell_condition2:
            direction = 'SELL'
            signal_candle_value = float(current_candle['low'])  # SCH = signal candle low
            signal_candle_data = {
                'high': float(current_candle['high']),
                'low': float(current_candle['low']),
                'open': float(current_candle['open']),
                'close': float(current_candle['close']),
                'date': current_candle['date']
            }
            print(f"✅ [SELL SIGNAL DETECTED] {symbol} at {check_timestamp}")
            print(f"   Signal Candle: {current_candle['date']} | Low: {signal_candle_value:.2f}")
        
        # If no signal detected
        if direction is None:
            return False
        
        # Get market type from params
        market_type = params.get('Market', 'IO')  # Default to IO if not specified
        
        # Calculate entry price
        entry_price = calculate_entry_price(signal_candle_value, direction, market_type)
        
        # Calculate initial stop loss
        initial_sl = calculate_initial_sl(
            signal_candle_data['low'],
            signal_candle_data['high'],
            direction,
            market_type
        )
        
        # Calculate all levels
        levels = calculate_levels(
            entry_price,
            direction,
            params.get('T1Percent', 1.0),
            params.get('T2Percent', 1.0),
            params.get('T3Percent', 1.0),
            params.get('T4Percent', 1.0),
            params.get('SL1Points', 0),
            params.get('Sl2Points', 0),
            params.get('Sl3Points', 0),
            params.get('Sl4Points', 0)
        )
        
        # Store signal state
        positions_state[unique_key] = {
            'signal_detected': True,
            'signal_time': datetime.now().isoformat(),
            'direction': direction,
            'SCH': signal_candle_value,
            'SCL': signal_candle_data['low'] if direction == 'BUY' else signal_candle_data['high'],
            'signal_candle': signal_candle_data,
            'Entry': entry_price,
            'InitialSL': initial_sl,
            'T1': levels['T1'],
            'T2': levels['T2'],
            'T3': levels['T3'],
            'T4': levels['T4'],
            'SL1': levels['SL1'],
            'SL2': levels['SL2'],
            'SL3': levels['SL3'],
            'SL4': levels['SL4'],
            'entry_taken': False,
            'position_state': 'waiting_entry',
            'remaining_lots': params.get('EntryLots', 0),
            't1_hit': False,
            't2_hit': False,
            't3_hit': False,
            't4_hit': False,
            'exited_today': False,
            'market_type': market_type
        }
        
        # Log signal details in exact format as OrderLog.txt
        signal_date_str = str(signal_candle_data['date'])
        if hasattr(signal_candle_data['date'], 'strftime'):
            signal_date_str = signal_candle_data['date'].strftime('%Y-%m-%d %H:%M:%S')
        
        message = f"[SIGNAL DETECTED] {params['Symbol']} at {datetime.now()}"
        write_to_order_logs(message)
        write_to_order_logs(f"  Signal Candle High (SCH): {signal_candle_data['high']:.2f}")
        write_to_order_logs(f"  Signal Candle Low (SCL): {signal_candle_data['low']:.2f}")
        write_to_order_logs(f"  Entry Price: {entry_price:.2f}")
        write_to_order_logs(f"  Initial Stop Loss: {initial_sl:.2f}")
        write_to_order_logs(f"  Target 1: {levels['T1']:.2f} | SL1: {levels['SL1']:.2f} | Exit Lots: {params.get('Tgt1Lots', 0)}")
        write_to_order_logs(f"  Target 2: {levels['T2']:.2f} | SL2: {levels['SL2']:.2f} | Exit Lots: {params.get('Tgt2Lots', 0)}")
        write_to_order_logs(f"  Target 3: {levels['T3']:.2f} | SL3: {levels['SL3']:.2f} | Exit Lots: {params.get('Tgt3Lots', 0)}")
        write_to_order_logs(f"  Target 4: {levels['T4']:.2f} | SL4: {levels['SL4']:.2f} | Exit Lots: {params.get('Tgt4Lots', 0)}")
        write_to_order_logs(f"  Entry Lot Size: {params.get('EntryLots', 0)}")
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
        
        # Print summary to console
        print(f"  Entry Price: {entry_price:.2f}")
        print(f"  T1: {levels['T1']:.2f}, T2: {levels['T2']:.2f}, T3: {levels['T3']:.2f}, T4: {levels['T4']:.2f}")
        print(f"  SL1: {levels['SL1']:.2f}, SL2: {levels['SL2']:.2f}, SL3: {levels['SL3']:.2f}, SL4: {levels['SL4']:.2f}")
        
        return True
        
    except Exception as e:
        print(f"Error checking signal for {params.get('Symbol', 'unknown')}: {e}")
        traceback.print_exc()
        return False

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

def print_dashboard(result_dict, positions_state):
    """
    Print a compact dashboard showing status of all symbols being monitored.
    """
    try:
        import os
        os.system('cls' if os.name == 'nt' else 'clear')  # Clear screen
        
        current_time = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M:%S')
        print(f"\n{'='*85}")
        print(f"TRADING DASHBOARD - {current_time}")
        print(f"{'='*85}")
        
        # Compact header
        print(f"{'Symbol':<18} {'Status':<20} {'LTP':<10} {'C1':<8} {'C2':<8}")
        print(f"{'-'*85}")
        
        for unique_key, params in result_dict.items():
            symbol = params.get('Symbol', 'N/A')
            # Truncate long symbol names
            if len(symbol) > 17:
                symbol = symbol[:14] + "..."
            
            ltp = params.get('FyresLtp')
            ltp_str = f"{ltp:.2f}" if ltp else "N/A"
            
            # Get position state
            pos_state = positions_state.get(unique_key, {})
            
            # Determine status (compact)
            if pos_state.get('exited_today'):
                status = "EXITED"
            elif pos_state.get('entry_taken'):
                direction = pos_state.get('direction', 'BUY')
                remaining_lots = pos_state.get('remaining_lots', 0)
                entry_price = pos_state.get('entry_price', pos_state.get('Entry', 0))
                pnl = (ltp - entry_price) * remaining_lots if ltp and entry_price else 0
                if pnl != 0:
                    status = f"{direction} {remaining_lots}L P&L:{pnl:+.0f}"
                else:
                    status = f"{direction} {remaining_lots}L"
            elif pos_state.get('signal_detected'):
                direction = pos_state.get('direction', 'BUY')
                entry_price = pos_state.get('Entry', 0)
                status = f"WAIT {direction}@{entry_price:.1f}"
            else:
                status = "NO SIGNAL"
            
            # Truncate status if too long
            if len(status) > 19:
                status = status[:16] + "..."
            
            # Get last 2 candles info (compact: just time and G/R)
            candle1_info = "N/A"
            candle2_info = "N/A"
            
            candle1 = pos_state.get('last_candle_1')
            candle2 = pos_state.get('last_candle_2')
            
            if candle1:
                time_str = candle1.get('date_str', 'N/A')
                if hasattr(candle1.get('date'), 'strftime'):
                    time_str = candle1['date'].strftime('%H:%M')
                color = 'G' if candle1.get('color') == 'GREEN' else 'R' if candle1.get('color') == 'RED' else '?'
                candle1_info = f"{time_str} {color}"
            
            if candle2:
                time_str = candle2.get('date_str', 'N/A')
                if hasattr(candle2.get('date'), 'strftime'):
                    time_str = candle2['date'].strftime('%H:%M')
                color = 'G' if candle2.get('color') == 'GREEN' else 'R' if candle2.get('color') == 'RED' else '?'
                candle2_info = f"{time_str} {color}"
            
            print(f"{symbol:<18} {status:<20} {ltp_str:<10} {candle1_info:<8} {candle2_info:<8}")
        
        print(f"{'-'*85}\n")
        
    except Exception as e:
        print(f"Error printing dashboard: {e}")
        traceback.print_exc()

def monitor_entry_exit(unique_key, params, positions_state):
    """
    Monitor for entry and exit conditions using LTP.
    Also handles StopTime-based position closing.
    """
    try:
        if unique_key not in positions_state:
            return
        
        pos_state = positions_state[unique_key]
        
        # Skip if already exited today
        if pos_state.get('exited_today'):
            return
        
        # Skip if no signal detected
        if not pos_state.get('signal_detected'):
            return
        
        ltp = params.get('FyresLtp')
        if ltp is None:
            return
        
        start_time = params.get("StartTime")
        stop_time = params.get("StopTime")
        current_time = datetime.now(pytz.timezone('Asia/Kolkata'))
        current_time_obj = current_time.time()
        
        # Check if current time has reached or passed StopTime
        # In intraday mode, close all open positions at StopTime
        if stop_time:
            try:
                stop_hour, stop_min = map(int, stop_time.split(':'))
                stop_time_obj = dt_time(stop_hour, stop_min)
                
                # If current time >= StopTime
                if current_time_obj >= stop_time_obj:
                    # If position is open (entry taken), close it
                    if pos_state.get('entry_taken') and not pos_state.get('squared_off_at_stoptime', False):
                        remaining_lots = pos_state.get('remaining_lots', 0)
                        if remaining_lots > 0:
                            direction = pos_state.get('direction', 'BUY')
                            # Place opposite order to close position
                            if direction == 'BUY':
                                place_sell_order(params["FyresSymbol"], remaining_lots, ltp, "INTRADAY")
                            else:  # SELL
                                place_buy_order(params["FyresSymbol"], remaining_lots, ltp, "INTRADAY")
                            
                            pos_state['exited_today'] = True
                            pos_state['position_state'] = 'squared_off_stoptime'
                            pos_state['squared_off_at_stoptime'] = True
                            pos_state['remaining_lots'] = 0
                            message = f"[SQUARE OFF - StopTime] {params['Symbol']} at {ltp:.2f}, Lots: {remaining_lots} (Intraday)"
                            print(message)
                            write_to_order_logs(message)
                            return
                    # If signal detected but entry not taken, mark as expired at StopTime
                    elif pos_state.get('signal_detected') and not pos_state.get('entry_taken') and not pos_state.get('exited_today'):
                        pos_state['exited_today'] = True
                        pos_state['position_state'] = 'expired_stoptime'
                        message = f"[SIGNAL EXPIRED - StopTime] {params['Symbol']} - Signal detected but entry not taken. Marked as expired at StopTime."
                        print(message)
                        write_to_order_logs(message)
                        return
            except Exception as e:
                print(f"Error checking StopTime for {params.get('Symbol', 'unknown')}: {e}")
        
        # Check if we're within trading hours
        if not is_time_between(start_time, stop_time):
            return
        
        entry_price = pos_state.get('Entry')
        if entry_price is None:
            return
        
        position_state = pos_state.get('position_state', 'waiting_entry')
        direction = pos_state.get('direction', 'BUY')
        
        # Entry Logic
        if position_state == 'waiting_entry':
            entry_triggered = False
            
            if direction == 'BUY' and ltp >= entry_price:
                entry_triggered = True
            elif direction == 'SELL' and ltp <= entry_price:
                entry_triggered = True
            
            if entry_triggered:
                # Take entry
                entry_lots = params.get("EntryLots", 0)
                if entry_lots > 0:
                    if direction == 'BUY':
                        response = place_buy_order(params["FyresSymbol"], entry_lots, ltp, "INTRADAY")
                    else:  # SELL
                        response = place_sell_order(params["FyresSymbol"], entry_lots, ltp, "INTRADAY")
                    
                    if response:
                        pos_state['entry_taken'] = True
                        pos_state['position_state'] = 'in_position'
                        pos_state['entry_price'] = ltp
                        pos_state['entry_time'] = datetime.now().isoformat()
                        pos_state['remaining_lots'] = entry_lots
                        pos_state['Entry'] = ltp
                        
                        # Recalculate levels with actual entry price
                        levels = calculate_levels(
                            ltp,  # Actual entry price
                            direction,
                            params.get('T1Percent', 1.0),
                            params.get('T2Percent', 1.0),
                            params.get('T3Percent', 1.0),
                            params.get('T4Percent', 1.0),
                            params.get('SL1Points', 0),
                            params.get('Sl2Points', 0),
                            params.get('Sl3Points', 0),
                            params.get('Sl4Points', 0)
                        )
                        
                        pos_state['T1'] = levels['T1']
                        pos_state['SL1'] = levels['SL1']
                        pos_state['T2'] = levels['T2']
                        pos_state['SL2'] = levels['SL2']
                        pos_state['T3'] = levels['T3']
                        pos_state['SL3'] = levels['SL3']
                        pos_state['T4'] = levels['T4']
                        pos_state['SL4'] = levels['SL4']
                        
                        # Log entry taken
                        message = f"[ENTRY PRICE REACHED] {params['Symbol']} - {direction} at {datetime.now()}"
                        write_to_order_logs(message)
                        write_to_order_logs(f"  Entry Price: {ltp:.2f}")
                        write_to_order_logs(f"  Taking {direction} position with {entry_lots} lots")
                        write_to_order_logs("")
                        
                        print(f"[ENTRY TAKEN] {params['Symbol']} - {direction} at {ltp:.2f}, Lots: {entry_lots}")
        
        # Exit Logic (only if entry is taken)
        if not pos_state.get('entry_taken'):
            return
        
        # Get all levels
        t1 = pos_state.get('T1', 0)
        sl1 = pos_state.get('SL1', 0)
        t2 = pos_state.get('T2', 0)
        sl2 = pos_state.get('SL2', 0)
        t3 = pos_state.get('T3', 0)
        sl3 = pos_state.get('SL3', 0)
        t4 = pos_state.get('T4', 0)
        sl4 = pos_state.get('SL4', 0)
        remaining_lots = pos_state.get('remaining_lots', 0)
        
        if remaining_lots <= 0:
            return
        
        # Get Initial SL
        initial_sl = pos_state.get('InitialSL', 0)
        
        # State machine for exits
        if position_state == 'in_position':
            # Check Initial SL
            if (direction == 'BUY' and ltp <= initial_sl) or (direction == 'SELL' and ltp >= initial_sl):
                # Exit all remaining lots
                if remaining_lots > 0:
                    if direction == 'BUY':
                        place_sell_order(params["FyresSymbol"], remaining_lots, ltp, "INTRADAY")
                    else:  # SELL
                        place_buy_order(params["FyresSymbol"], remaining_lots, ltp, "INTRADAY")
                    
                    pos_state['exited_today'] = True
                    pos_state['position_state'] = 'exited_sl1'
                    pos_state['remaining_lots'] = 0
                    message = f"[EXIT - SL1] {params['Symbol']} at {ltp:.2f}, Lots: {remaining_lots}. All positions closed."
                    print(message)
                    write_to_order_logs(message)
                    return
            
            # Check T1
            if (direction == 'BUY' and ltp >= t1) or (direction == 'SELL' and ltp <= t1):
                tgt1_lots = params.get("Tgt1Lots", 0)
                if tgt1_lots > 0 and remaining_lots >= tgt1_lots:
                    if direction == 'BUY':
                        place_sell_order(params["FyresSymbol"], tgt1_lots, ltp, "INTRADAY")
                    else:  # SELL
                        place_buy_order(params["FyresSymbol"], tgt1_lots, ltp, "INTRADAY")
                    
                    pos_state['remaining_lots'] -= tgt1_lots
                    pos_state['t1_hit'] = True
                    pos_state['position_state'] = 't1_hit'
                    message = f"[T1 HIT] {params['Symbol']} at {ltp:.2f}, Exited: {tgt1_lots} lots, Remaining: {pos_state['remaining_lots']}"
                    print(message)
                    write_to_order_logs(message)

        elif position_state == 't1_hit':
            # Check SL2 or T2
            if (direction == 'BUY' and ltp <= sl2) or (direction == 'SELL' and ltp >= sl2):
                # Exit all remaining lots
                if remaining_lots > 0:
                    if direction == 'BUY':
                        place_sell_order(params["FyresSymbol"], remaining_lots, ltp, "INTRADAY")
                    else:  # SELL
                        place_buy_order(params["FyresSymbol"], remaining_lots, ltp, "INTRADAY")
                    
                    pos_state['exited_today'] = True
                    pos_state['position_state'] = 'exited_sl2'
                    pos_state['remaining_lots'] = 0
                    message = f"[EXIT - SL2] {params['Symbol']} at {ltp:.2f}, Lots: {remaining_lots}. All positions closed."
                    print(message)
                    write_to_order_logs(message)
                    return
            elif (direction == 'BUY' and ltp >= t2) or (direction == 'SELL' and ltp <= t2):
                tgt2_lots = params.get("Tgt2Lots", 0)
                if tgt2_lots > 0 and remaining_lots >= tgt2_lots:
                    if direction == 'BUY':
                        place_sell_order(params["FyresSymbol"], tgt2_lots, ltp, "INTRADAY")
                    else:  # SELL
                        place_buy_order(params["FyresSymbol"], tgt2_lots, ltp, "INTRADAY")
                    
                    pos_state['remaining_lots'] -= tgt2_lots
                    pos_state['t2_hit'] = True
                    pos_state['position_state'] = 't2_hit'
                    message = f"[T2 HIT] {params['Symbol']} at {ltp:.2f}, Exited: {tgt2_lots} lots, Remaining: {pos_state['remaining_lots']}"
                    print(message)
                    write_to_order_logs(message)

        elif position_state == 't2_hit':
            # Check SL3 or T3
            if (direction == 'BUY' and ltp <= sl3) or (direction == 'SELL' and ltp >= sl3):
                # Exit all remaining lots
                if remaining_lots > 0:
                    if direction == 'BUY':
                        place_sell_order(params["FyresSymbol"], remaining_lots, ltp, "INTRADAY")
                    else:  # SELL
                        place_buy_order(params["FyresSymbol"], remaining_lots, ltp, "INTRADAY")
                    
                    pos_state['exited_today'] = True
                    pos_state['position_state'] = 'exited_sl3'
                    pos_state['remaining_lots'] = 0
                    message = f"[EXIT - SL3] {params['Symbol']} at {ltp:.2f}, Lots: {remaining_lots}. All positions closed."
                    print(message)
                    write_to_order_logs(message)
                    return
            elif (direction == 'BUY' and ltp >= t3) or (direction == 'SELL' and ltp <= t3):
                tgt3_lots = params.get("Tgt3Lots", 0)
                if tgt3_lots > 0 and remaining_lots >= tgt3_lots:
                    if direction == 'BUY':
                        place_sell_order(params["FyresSymbol"], tgt3_lots, ltp, "INTRADAY")
                    else:  # SELL
                        place_buy_order(params["FyresSymbol"], tgt3_lots, ltp, "INTRADAY")
                    
                    pos_state['remaining_lots'] -= tgt3_lots
                    pos_state['t3_hit'] = True
                    pos_state['position_state'] = 't3_hit'
                    message = f"[T3 HIT] {params['Symbol']} at {ltp:.2f}, Exited: {tgt3_lots} lots, Remaining: {pos_state['remaining_lots']}"
                    print(message)
                    write_to_order_logs(message)

        elif position_state == 't3_hit':
            # Check SL4 or T4
            if (direction == 'BUY' and ltp <= sl4) or (direction == 'SELL' and ltp >= sl4):
                # Exit all remaining lots
                if remaining_lots > 0:
                    if direction == 'BUY':
                        place_sell_order(params["FyresSymbol"], remaining_lots, ltp, "INTRADAY")
                    else:  # SELL
                        place_buy_order(params["FyresSymbol"], remaining_lots, ltp, "INTRADAY")
                    
                    pos_state['exited_today'] = True
                    pos_state['position_state'] = 'exited_sl4'
                    pos_state['remaining_lots'] = 0
                    message = f"[EXIT - SL4] {params['Symbol']} at {ltp:.2f}, Lots: {remaining_lots}. All positions closed."
                    print(message)
                    write_to_order_logs(message)
                    return
            elif (direction == 'BUY' and ltp >= t4) or (direction == 'SELL' and ltp <= t4):
                # T4 hit - exit ALL remaining lots
                if remaining_lots > 0:
                    if direction == 'BUY':
                        place_sell_order(params["FyresSymbol"], remaining_lots, ltp, "INTRADAY")
                    else:  # SELL
                        place_buy_order(params["FyresSymbol"], remaining_lots, ltp, "INTRADAY")
                    
                    pos_state['remaining_lots'] = 0
                    pos_state['t4_hit'] = True
                    pos_state['position_state'] = 't4_hit'
                    pos_state['exited_today'] = True
                    message = f"[T4 HIT] {params['Symbol']} at {ltp:.2f}, Exited ALL {remaining_lots} lots. All positions closed."
                    print(message)
                    write_to_order_logs(message)
                    return
    
    except Exception as e:
        print(f"Error monitoring entry/exit for {params.get('Symbol', 'unknown')}: {e}")
        traceback.print_exc()

def main_strategy():
    """
    Main strategy function that handles signal detection.
    Runs timeframe-based checks for each symbol.
    """
    try:
        global result_dict, positions_state
        
        # Update LTP data
        UpdateData()
        
        now = datetime.now(pytz.timezone('Asia/Kolkata'))
        
        # Loop through each symbol and check for signals at timeframe intervals
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
                # Set first check time to StartTime + 1 second (e.g., 9:30:01)
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
            
            # Convert string back to datetime
            if isinstance(next_check_time, str):
                next_check_time = datetime.fromisoformat(next_check_time)
                # Ensure timezone-aware (in case it was saved as naive)
                if next_check_time.tzinfo is None:
                    next_check_time = pytz.timezone('Asia/Kolkata').localize(next_check_time)
            
            # Check if it's time to check for signal (every timeframe minutes)
            if now >= next_check_time:
                # Only check signals during trading hours
                start_time = params.get("StartTime")
                stop_time = params.get("StopTime")
                if is_time_between(start_time, stop_time):
                    # Check for signal (this also updates candle data)
                    signal_detected = check_signal_for_symbol(unique_key, params, positions_state)
                else:
                    # Even if not in trading hours, update candle data for dashboard
                    update_candle_data_for_dashboard(unique_key, params, positions_state)
                
                # Update next check time to next timeframe interval
                normalized_time = normalize_time_to_timeframe(now, timeframe)
                next_check_time = normalized_time + timedelta(minutes=timeframe)
                pos_state['next_check_time'] = next_check_time.isoformat()
            
            # Also update candle data immediately when StartTime is reached (even if not time for signal check yet)
            start_time = params.get("StartTime")
            if start_time:
                try:
                    start_hour, start_min = map(int, start_time.split(':'))
                    today = now.date()
                    start_datetime = pytz.timezone('Asia/Kolkata').localize(datetime.combine(today, dt_time(start_hour, start_min)))
                    # If StartTime was just reached (within last 5 seconds), update candle data
                    time_since_start = (now - start_datetime).total_seconds()
                    if 0 <= time_since_start <= 5:
                        update_candle_data_for_dashboard(unique_key, params, positions_state)
                except:
                    pass
        
        # Phase 2: Monitor entry/exit for all symbols (runs every second)
        # This includes checking StopTime for position closing
        for unique_key, params in result_dict.items():
            monitor_entry_exit(unique_key, params, positions_state)
        
        # Update candle data for dashboard every 10 seconds (for all symbols)
        if not hasattr(main_strategy, 'last_candle_update_time'):
            main_strategy.last_candle_update_time = now - timedelta(seconds=11)  # Force immediate update on first run
        
        time_since_last_candle_update = (now - main_strategy.last_candle_update_time).total_seconds()
        if time_since_last_candle_update >= 10:  # Update candle data every 10 seconds
            for unique_key, params in result_dict.items():
                update_candle_data_for_dashboard(unique_key, params, positions_state)
            main_strategy.last_candle_update_time = now
        
        # Print dashboard every 5 seconds
        if not hasattr(main_strategy, 'last_dashboard_time'):
            main_strategy.last_dashboard_time = now
        
        time_since_last_dashboard = (now - main_strategy.last_dashboard_time).total_seconds()
        if time_since_last_dashboard >= 5:  # Update dashboard every 5 seconds
            print_dashboard(result_dict, positions_state)
            main_strategy.last_dashboard_time = now
               
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
        timeframe = params.get('Timeframe', 'N/A')
        start_time = params.get('StartTime', 'N/A')
        stop_time = params.get('StopTime', 'N/A')
        market = params.get('Market', 'N/A')
        print(f"  - {params['Symbol']} (Market: {market}, Timeframe: {timeframe} min, StartTime: {start_time}, StopTime: {stop_time})")
    print(f"{'='*80}\n")
    
    write_to_order_logs(f"\n{'='*80}")
    write_to_order_logs(f"[PROJECT START] Trading Strategy Started at {startup_time.strftime('%Y-%m-%d %H:%M:%S')}")
    write_to_order_logs(f"[STARTUP] Strategy initialized at {startup_time}")
    write_to_order_logs(f"[STARTUP] Loaded {len(result_dict)} symbol(s) from TradeSettings.csv")
    for unique_key, params in result_dict.items():
        timeframe = params.get('Timeframe', 'N/A')
        start_time = params.get('StartTime', 'N/A')
        stop_time = params.get('StopTime', 'N/A')
        market = params.get('Market', 'N/A')
        write_to_order_logs(f"  - {params['Symbol']} (Market: {market}, Timeframe: {timeframe} min, StartTime: {start_time}, StopTime: {stop_time})")
    write_to_order_logs(f"{'='*80}\n")
    
    # Initialize state - start fresh every time
    global positions_state
    positions_state = {}
    print("[STATE] Starting fresh - no previous state loaded")
    print("[STATE] Will wait for StartTime and check patterns from there")
    write_to_order_logs("[STATE] Starting fresh - no previous state loaded")
    write_to_order_logs("[STATE] Will wait for StartTime and check patterns from there")
    
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
         
    
