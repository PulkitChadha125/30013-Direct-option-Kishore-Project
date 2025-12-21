import pandas as pd
from datetime import datetime, timedelta, time as dt_time
import polars as pl
import polars_talib as plta
import json
import time
import traceback
import sys
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
        file.write(message + '\n')

def load_state():
    """Load state from state.json file - returns positions even if from different day"""
    try:
        with open('state.json', 'r') as f:
            state = json.load(f)
            return state.get('positions', {}), state.get('date')
    except FileNotFoundError:
        return {}, None
    except Exception as e:
        print(f"Error loading state: {e}")
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

def check_signal_candle(df):
    """
    Check for signal candle based on new logic:
    1. Check first candle of present day - if green, it's signal candle
    2. If first candle is red, check green candle pattern:
       - Previous candle is green
       - Previous candle High < prev to previous candle's High
       - Previous candle Low < prev to previous candle's Low
    Returns (is_signal, signal_candle_data) where signal_candle_data is dict with high, low, open, close
    """
    if len(df) < 2:
        return False, None
    
    # Get today's date
    today = datetime.now().date()
    
    # Filter candles for today only (without modifying original dataframe)
    df_copy = df.copy()
    df_copy['date_only'] = pd.to_datetime(df_copy['date']).dt.date
    today_candles = df_copy[df_copy['date_only'] == today].copy()
    
    # If no candles for today, return False
    if len(today_candles) == 0:
        return False, None
    
    # Get first candle of today (sorted by time to ensure first candle)
    today_candles = today_candles.sort_values('date')
    first_candle_today = today_candles.iloc[0]
    
    # Check if first candle is green (close > open)
    is_first_green = first_candle_today['close'] > first_candle_today['open']
    
    if is_first_green:
        # First candle is green - it's our signal candle
        signal_candle = {
            'high': float(first_candle_today['high']),
            'low': float(first_candle_today['low']),
            'open': float(first_candle_today['open']),
            'close': float(first_candle_today['close'])
        }
        return True, signal_candle
    
    # First candle is red - check for green candle pattern
    # We need at least 3 candles total (including today's first red candle)
    if len(df) < 3:
        return False, None
    
    # Get last 3 candles (most recent is last)
    candle_3 = df.iloc[-3]  # Oldest of the 3
    candle_2 = df.iloc[-2]  # Middle (the green candle we're checking)
    candle_1 = df.iloc[-1]  # Most recent
    
    # Check if candle_2 is green (close > open)
    is_green = candle_2['close'] > candle_2['open']
    
    if not is_green:
        return False, None
    
    # Check conditions for green candle pattern:
    # Previous candle High < prev to previous candle's High
    # Previous candle Low < prev to previous candle's Low
    condition1 = candle_2['high'] < candle_3['high']
    condition2 = candle_2['low'] < candle_3['low']
    
    if condition1 and condition2:
        signal_candle = {
            'high': float(candle_2['high']),
            'low': float(candle_2['low']),
            'open': float(candle_2['open']),
            'close': float(candle_2['close'])
        }
        return True, signal_candle
    
    return False, None

def calculate_levels(signal_candle, actual_entry_price, t2_percent, t3_percent, t4_percent, sl1_points, sl2_points, sl3_points, sl4_points):
    """
    Calculate all entry, exit, and target levels based on signal candle
    entry_price is the actual entry price (EP) used for target calculations
    Entry trigger is always calculated from SCH
    Returns dict with all calculated levels
    """
    import math
    
    SCH = signal_candle['high']
    SCL = signal_candle['low']
    
    # Entry trigger = SCH + (√(SCH) × 26.11%)
    entry_trigger = SCH + (math.sqrt(SCH) * 0.2611)
    
    # Initial SL = SCL - (√(SCL) × 26.11%)
    initial_sl = SCL - (math.sqrt(SCL) * 0.2611)
    
    # Targets are calculated from actual entry price (EP)
    # T1 = EP + 13.06%
    t1 = actual_entry_price + (actual_entry_price * 0.1306)
    sl1 = t1 - sl1_points
    
    # T2 = EP + T2Percent%
    t2 = actual_entry_price + (actual_entry_price * t2_percent / 100)
    sl2 = t2 - sl2_points
    
    # T3 = EP + T3Percent%
    t3 = actual_entry_price + (actual_entry_price * t3_percent / 100)
    sl3 = t3 - sl3_points
    
    # T4 = EP + T4Percent%
    t4 = actual_entry_price + (actual_entry_price * t4_percent / 100)
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
    Print comprehensive trading status for a symbol in a presentable format
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
        
        current_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print("\n" + "="*80)
        print(f"{status_color} TRADING STATUS: {symbol} | LTP: {ltp_str} | Status: {status}")
        print(f"   Time: {current_timestamp}")
        print("="*80)
        
        # Signal Candle Information
        if pos_state.get('signal_detected'):
            sch = pos_state.get('SCH', 0)
            scl = pos_state.get('SCL', 0)
            signal_time = pos_state.get('signal_time', 'N/A')
            if isinstance(signal_time, str) and 'T' in signal_time:
                signal_time = signal_time.split('T')[1].split('.')[0]
            
            print(f"\n📊 SIGNAL CANDLE:")
            print(f"   SCH (Signal Candle High): {sch:.2f}")
            print(f"   SCL (Signal Candle Low):  {scl:.2f}")
            print(f"   Signal Detected At:       {signal_time}")
        
        # Entry Information
        entry_price = pos_state.get('Entry', 0)
        entry_lots = params.get('EntryLots', 0)
        entry_taken = pos_state.get('entry_taken', False)
        actual_entry_price = pos_state.get('entry_price', entry_price)
        entry_time = pos_state.get('entry_time', 'N/A')
        if isinstance(entry_time, str) and 'T' in entry_time:
            entry_time = entry_time.split('T')[1].split('.')[0]
        
        print(f"\n🎯 ENTRY:")
        if entry_taken:
            print(f"   Entry Price:              {actual_entry_price:.2f} ✅ ENTERED")
            print(f"   Entry Time:               {entry_time}")
            print(f"   Entry Lots:               {entry_lots}")
        else:
            print(f"   Entry Trigger:             {entry_price:.2f} ⏳ WAITING")
            print(f"   Entry Lots:                {entry_lots}")
            if ltp:
                diff = entry_price - ltp
                pct_diff = (diff / ltp * 100) if ltp > 0 else 0
                print(f"   Distance to Entry:        {diff:.2f} points ({pct_diff:+.2f}%)")
        
        # Stop Loss Information
        initial_sl = pos_state.get('InitialSL', 0)
        print(f"\n🛑 STOP LOSS LEVELS:")
        if initial_sl > 0:
            print(f"   Initial SL:                {initial_sl:.2f}")
            if entry_taken and ltp:
                sl_diff = ltp - initial_sl
                sl_pct = (sl_diff / ltp * 100) if ltp > 0 else 0
                print(f"   SL Distance:               {sl_diff:.2f} points ({sl_pct:.2f}%)")
        
        # Target and SL Information
        t1 = pos_state.get('T1', 0)
        t2 = pos_state.get('T2', 0)
        t3 = pos_state.get('T3', 0)
        t4 = pos_state.get('T4', 0)
        sl1 = pos_state.get('SL1', 0)
        sl2 = pos_state.get('SL2', 0)
        sl3 = pos_state.get('SL3', 0)
        sl4 = pos_state.get('SL4', 0)
        
        tgt1_lots = params.get('Tgt1Lots', 0)
        tgt2_lots = params.get('Tgt2Lots', 0)
        tgt3_lots = params.get('Tgt3Lots', 0)
        tgt4_lots = params.get('Tgt4Lots', 0)
        
        t1_hit = pos_state.get('t1_hit', False)
        t2_hit = pos_state.get('t2_hit', False)
        t3_hit = pos_state.get('t3_hit', False)
        t4_hit = pos_state.get('t4_hit', False)
        
        print(f"\n🎯 TARGETS & STOP LOSSES:")
        print(f"   {'Target':<12} {'Price':<12} {'SL Below':<12} {'Exit Lots':<12} {'Status':<12}")
        print(f"   {'-'*12} {'-'*12} {'-'*12} {'-'*12} {'-'*12}")
        
        if t1 > 0:
            t1_status = "✅ HIT" if t1_hit else ("🟢 ACTIVE" if entry_taken else "⏳ PENDING")
            if ltp and entry_taken:
                t1_diff = t1 - ltp
                t1_pct = (t1_diff / ltp * 100) if ltp > 0 else 0
                t1_info = f"{t1_diff:+.2f} ({t1_pct:+.2f}%)"
            else:
                t1_info = "-"
            print(f"   T1{'':<9} {t1:<12.2f} {sl1:<12.2f} {tgt1_lots:<12} {t1_status:<12} {t1_info}")
        
        if t2 > 0:
            t2_status = "✅ HIT" if t2_hit else ("🟢 ACTIVE" if t1_hit else "⏳ PENDING")
            if ltp and entry_taken and t1_hit:
                t2_diff = t2 - ltp
                t2_pct = (t2_diff / ltp * 100) if ltp > 0 else 0
                t2_info = f"{t2_diff:+.2f} ({t2_pct:+.2f}%)"
            else:
                t2_info = "-"
            print(f"   T2{'':<9} {t2:<12.2f} {sl2:<12.2f} {tgt2_lots:<12} {t2_status:<12} {t2_info}")
        
        if t3 > 0:
            t3_status = "✅ HIT" if t3_hit else ("🟢 ACTIVE" if t2_hit else "⏳ PENDING")
            if ltp and entry_taken and t2_hit:
                t3_diff = t3 - ltp
                t3_pct = (t3_diff / ltp * 100) if ltp > 0 else 0
                t3_info = f"{t3_diff:+.2f} ({t3_pct:+.2f}%)"
            else:
                t3_info = "-"
            print(f"   T3{'':<9} {t3:<12.2f} {sl3:<12.2f} {tgt3_lots:<12} {t3_status:<12} {t3_info}")
        
        if t4 > 0:
            t4_status = "✅ HIT" if t4_hit else ("🟢 ACTIVE" if t3_hit else "⏳ PENDING")
            if ltp and entry_taken and t3_hit:
                t4_diff = t4 - ltp
                t4_pct = (t4_diff / ltp * 100) if ltp > 0 else 0
                t4_info = f"{t4_diff:+.2f} ({t4_pct:+.2f}%)"
            else:
                t4_info = "-"
            print(f"   T4{'':<9} {t4:<12.2f} {sl4:<12.2f} {tgt4_lots:<12} {t4_status:<12} {t4_info}")
        
        # Position Summary
        if entry_taken:
            remaining_lots = pos_state.get('remaining_lots', 0)
            pnl = 0
            if ltp and actual_entry_price:
                pnl = (ltp - actual_entry_price) * remaining_lots
                pnl_pct = ((ltp - actual_entry_price) / actual_entry_price * 100) if actual_entry_price > 0 else 0
            
            print(f"\n💰 POSITION SUMMARY:")
            print(f"   Remaining Lots:            {remaining_lots}")
            if ltp and actual_entry_price:
                print(f"   Unrealized P&L:            {pnl:+.2f} ({pnl_pct:+.2f}%)")
        
        # Trading Hours
        start_time = params.get('StartTime', 'N/A')
        stop_time = params.get('StopTime', 'N/A')
        current_time = datetime.now().time()
        in_trading_hours = is_time_between(start_time, stop_time, current_time) if start_time != 'N/A' else True
        
        print(f"\n⏰ TRADING HOURS:")
        print(f"   Start Time:                {start_time}")
        print(f"   Stop Time:                 {stop_time}")
        print(f"   Current Status:            {'🟢 ACTIVE' if in_trading_hours else '🔴 OUT OF HOURS'}")
        
        # Next Pattern Check Time
        next_check_time = pos_state.get('next_check_time')
        timeframe = params.get('Timeframe', 'N/A')
        if next_check_time:
            try:
                if isinstance(next_check_time, str):
                    next_check_dt = datetime.fromisoformat(next_check_time)
                else:
                    next_check_dt = next_check_time
                
                now = datetime.now()
                time_until_check = next_check_dt - now
                
                # Format next check time
                next_check_str = next_check_dt.strftime("%Y-%m-%d %H:%M:%S")
                
                # Calculate time remaining
                if time_until_check.total_seconds() > 0:
                    hours = int(time_until_check.total_seconds() // 3600)
                    minutes = int((time_until_check.total_seconds() % 3600) // 60)
                    seconds = int(time_until_check.total_seconds() % 60)
                    
                    if hours > 0:
                        time_remaining = f"{hours}h {minutes}m {seconds}s"
                    elif minutes > 0:
                        time_remaining = f"{minutes}m {seconds}s"
                    else:
                        time_remaining = f"{seconds}s"
                    
                    print(f"\n🔄 PATTERN DETECTION:")
                    print(f"   Timeframe:                {timeframe} minutes")
                    print(f"   Next Check Time:           {next_check_str}")
                    print(f"   Time Remaining:           {time_remaining}")
                else:
                    print(f"\n🔄 PATTERN DETECTION:")
                    print(f"   Timeframe:                {timeframe} minutes")
                    print(f"   Next Check Time:           {next_check_str} (DUE NOW)")
            except Exception as e:
                print(f"\n🔄 PATTERN DETECTION:")
                print(f"   Timeframe:                {timeframe} minutes")
                print(f"   Next Check Time:           Calculating...")
        else:
            print(f"\n🔄 PATTERN DETECTION:")
            print(f"   Timeframe:                {timeframe} minutes")
            print(f"   Next Check Time:           Not scheduled yet")
        
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"Error printing trading status: {e}")
        traceback.print_exc()

def get_user_settings():
    global result_dict, instrument_id_list, Equity_instrument_id_list, Future_instrument_id_list, FyerSymbolList, positions_state
    import pandas as pd

    delete_file_contents("OrderLog.txt")

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
        
        # Fetch historical data
        df = fetchOHLC(symbol, timeframe)
        
        if len(df) < 3:
            return False
        
        # Check for signal candle
        is_signal, signal_candle = check_signal_candle(df)
        
        if is_signal:
            # Print last 2 rows
            print(f"\n[SIGNAL DETECTED] {symbol} at {datetime.now()}")
            print("Last 2 candles:")
            print(df.tail(2))
            
            # Calculate levels (using SCH as estimated entry price for initial calculation)
            # Will recalculate with actual entry price when entry is taken
            levels = calculate_levels(
                signal_candle,
                signal_candle['high'],  # Use SCH as estimated EP for initial target calculation
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
            
            message = f"[SIGNAL] {symbol} - SCH: {levels['SCH']:.2f}, SCL: {levels['SCL']:.2f}, Entry: {levels['Entry']:.2f}"
            print(message)
            write_to_order_logs(message)
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
        
        # Skip if no signal detected
        if not pos_state.get('signal_detected'):
            return
        
        # Track last status print time
        current_time = datetime.now()
        last_status_print = pos_state.get('last_status_print')
        
        # Print status every 30 seconds or on first signal
        should_print_status = False
        if last_status_print is None:
            should_print_status = True
            pos_state['last_status_print'] = current_time.isoformat()
        else:
            if isinstance(last_status_print, str):
                last_status_print = datetime.fromisoformat(last_status_print)
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
                
                message = f"[ENTRY TAKEN] {params['Symbol']} at {ltp:.2f}, Lots: {entry_lots}, T1: {levels['T1']:.2f}, T2: {levels['T2']:.2f}, T3: {levels['T3']:.2f}, T4: {levels['T4']:.2f}"
                print(message)
                write_to_order_logs(message)
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
        
        now = datetime.now()
        
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
                normalized_time = normalize_time_to_timeframe(now, timeframe)
                next_check_time = normalized_time + timedelta(minutes=timeframe)
                pos_state['next_check_time'] = next_check_time.isoformat()
                save_state(positions_state)
            
            # Convert string back to datetime
            if isinstance(next_check_time, str):
                next_check_time = datetime.fromisoformat(next_check_time)
            
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
        
        # Print status for symbols with signals or open positions (even if not in monitoring mode yet)
        for unique_key, params in result_dict.items():
            pos_state = positions_state.get(unique_key, {})
            if pos_state.get('signal_detected') or pos_state.get('entry_taken'):
                # Only print if not already printed in monitor_entry_exit
                current_time = datetime.now()
                last_status_print = pos_state.get('last_status_print')
                if last_status_print is None:
                    print_trading_status(unique_key, params, positions_state)
                    pos_state['last_status_print'] = current_time.isoformat()
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
                print(f"[STATE] Clearing exited position for {pos_state.get('Symbol', key)} (ProductType: {product_type}) - will check for fresh pattern")
                positions_state[key] = {}  # Clear state for fresh pattern check
            elif pos_state.get('entry_taken'):
                # Position is still open
                if product_type == 'positional':
                    # Positional: continue monitoring it
                    print(f"[STATE] Carrying forward OPEN POSITIONAL position for {pos_state.get('Symbol', key)}")
                    print(f"        Entry Price: {pos_state.get('entry_price', 'N/A')}")
                    print(f"        Remaining Lots: {pos_state.get('remaining_lots', 0)}")
                    print(f"        Position State: {pos_state.get('position_state', 'N/A')}")
                    # Reset exited_today flag for new day
                    pos_state['exited_today'] = False
                else:
                    # Intraday: should have been squared off at StopTime, but if not, clear it
                    print(f"[STATE] Clearing intraday position for {pos_state.get('Symbol', key)} - should have been squared off at StopTime")
                    positions_state[key] = {}  # Clear state for fresh pattern check
            elif pos_state.get('signal_detected') and not pos_state.get('entry_taken'):
                # Signal detected but entry not taken
                if product_type == 'positional':
                    # Positional: continue waiting for entry
                    print(f"[STATE] Carrying forward SIGNAL for {pos_state.get('Symbol', key)} (Positional) - still waiting for entry")
                    pos_state['exited_today'] = False
                else:
                    # Intraday: clear signal for fresh check today
                    print(f"[STATE] Clearing intraday signal for {pos_state.get('Symbol', key)} - will check for fresh pattern")
                    positions_state[key] = {}  # Clear state for fresh pattern check
            else:
                # Empty or invalid state - clear it
                positions_state[key] = {}
        
        # Save updated state
        save_state(positions_state)
        print("[STATE] State updated for new trading day\n")
    elif state_date == today:
        print(f"[STATE] Loading state from today: {today}")
        open_positions = [k for k, v in positions_state.items() if v.get('entry_taken')]
        if open_positions:
            print(f"[STATE] Found {len(open_positions)} open position(s) to monitor")
    else:
        print("[STATE] No previous state found - starting fresh")
        print("[STATE] All symbols will check for fresh green candle patterns")
        print("[STATE] No carry-forward positions - clean start")

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
         
    
