import pandas as pd
import datetime  # full module
import polars as pl
import polars_talib as plta
import json
# from datetime import datetime, timedelta
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
    """Load state from state.json file"""
    try:
        with open('state.json', 'r') as f:
            state = json.load(f)
            # Check if state is from today, if not reset
            today = datetime.datetime.now().date().isoformat()
            if state.get('date') != today:
                return {}
            return state.get('positions', {})
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"Error loading state: {e}")
        return {}

def save_state(positions_state):
    """Save state to state.json file"""
    try:
        state = {
            'date': datetime.datetime.now().date().isoformat(),
            'positions': positions_state
        }
        with open('state.json', 'w') as f:
            json.dump(state, f, indent=2, default=str)
    except Exception as e:
        print(f"Error saving state: {e}")

def is_time_between(start_time_str, stop_time_str, current_time=None):
    """Check if current time is between start_time and stop_time"""
    if current_time is None:
        current_time = datetime.datetime.now().time()
    
    try:
        # Parse time strings (format: "HH:MM")
        start_hour, start_min = map(int, start_time_str.split(':'))
        stop_hour, stop_min = map(int, stop_time_str.split(':'))
        
        start = datetime.time(start_hour, start_min)
        stop = datetime.time(stop_hour, stop_min)
        
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
    Check if the last 3 candles meet the signal criteria.
    Returns (is_signal, signal_candle_data) where signal_candle_data is dict with high, low, open, close
    """
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
    
    # Check conditions:
    # Green candle high < previous candle high
    # Green candle low > previous candle low
    condition1 = candle_2['high'] < candle_3['high']
    condition2 = candle_2['low'] > candle_3['low']
    
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

def place_buy_order(symbol, quantity, price):
    """Place a buy order (Market order)"""
    try:
        from FyresIntegration import place_order
        response = place_order(symbol=symbol, quantity=quantity, type=2, side=1, price=price)
        message = f"[BUY ORDER] {datetime.datetime.now()} - Symbol: {symbol}, Qty: {quantity}, Price: {price}, Response: {response}"
        print(message)
        write_to_order_logs(message)
        return response
    except Exception as e:
        error_msg = f"[BUY ORDER ERROR] {datetime.datetime.now()} - Symbol: {symbol}, Error: {str(e)}"
        print(error_msg)
        write_to_order_logs(error_msg)
        return None

def place_sell_order(symbol, quantity, price):
    """Place a sell order (Market order)"""
    try:
        from FyresIntegration import place_order
        response = place_order(symbol=symbol, quantity=quantity, type=2, side=-1, price=price)
        message = f"[SELL ORDER] {datetime.datetime.now()} - Symbol: {symbol}, Qty: {quantity}, Price: {price}, Response: {response}"
        print(message)
        write_to_order_logs(message)
        return response
    except Exception as e:
        error_msg = f"[SELL ORDER ERROR] {datetime.datetime.now()} - Symbol: {symbol}, Error: {str(e)}"
        print(error_msg)
        write_to_order_logs(error_msg)
        return None

def get_user_settings():
    global result_dict, instrument_id_list, Equity_instrument_id_list, Future_instrument_id_list, FyerSymbolList
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
            print(f"\n[SIGNAL DETECTED] {symbol} at {datetime.datetime.now()}")
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
                'signal_time': datetime.datetime.now().isoformat(),
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
        
        ltp = params.get('FyresLtp')
        if ltp is None:
            return
        
        start_time = params["StartTime"]
        stop_time = params["StopTime"]
        
        # Check if we're within trading hours
        if not is_time_between(start_time, stop_time):
            return
        
        entry_price = pos_state['Entry']
        position_state = pos_state.get('position_state', 'waiting_entry')
        
        # Entry Logic
        if position_state == 'waiting_entry' and ltp >= entry_price:
            # Take entry
            entry_lots = params["EntryLots"]
            response = place_buy_order(params["FyresSymbol"], entry_lots, ltp)
            
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
                pos_state['entry_time'] = datetime.datetime.now().isoformat()
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
        
        # Exit Logic (only if entry is taken)
        if not pos_state.get('entry_taken'):
            return
        
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
                    place_sell_order(params["FyresSymbol"], remaining_lots, ltp)
                    pos_state['exited_today'] = True
                    pos_state['position_state'] = 'exited_sl'
                    message = f"[EXIT - Initial SL] {params['Symbol']} at {ltp:.2f}, Lots: {remaining_lots}"
                    print(message)
                    write_to_order_logs(message)
                    save_state(positions_state)
                return
            
            # Check T1
            if ltp >= t1:
                tgt1_lots = params["Tgt1Lots"]
                if tgt1_lots > 0 and remaining_lots >= tgt1_lots:
                    place_sell_order(params["FyresSymbol"], tgt1_lots, ltp)
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
                    place_sell_order(params["FyresSymbol"], remaining_lots, ltp)
                    pos_state['exited_today'] = True
                    pos_state['position_state'] = 'exited_sl1'
                    message = f"[EXIT - SL1] {params['Symbol']} at {ltp:.2f}, Lots: {remaining_lots}"
                    print(message)
                    write_to_order_logs(message)
                    save_state(positions_state)
            elif ltp >= t2:
                tgt2_lots = params["Tgt2Lots"]
                if tgt2_lots > 0 and remaining_lots >= tgt2_lots:
                    place_sell_order(params["FyresSymbol"], tgt2_lots, ltp)
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
                    place_sell_order(params["FyresSymbol"], remaining_lots, ltp)
                    pos_state['exited_today'] = True
                    pos_state['position_state'] = 'exited_sl2'
                    message = f"[EXIT - SL2] {params['Symbol']} at {ltp:.2f}, Lots: {remaining_lots}"
                    print(message)
                    write_to_order_logs(message)
                    save_state(positions_state)
            elif ltp >= t3:
                tgt3_lots = params["Tgt3Lots"]
                if tgt3_lots > 0 and remaining_lots >= tgt3_lots:
                    place_sell_order(params["FyresSymbol"], tgt3_lots, ltp)
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
                    place_sell_order(params["FyresSymbol"], remaining_lots, ltp)
                    pos_state['exited_today'] = True
                    pos_state['position_state'] = 'exited_sl3'
                    message = f"[EXIT - SL3] {params['Symbol']} at {ltp:.2f}, Lots: {remaining_lots}"
                    print(message)
                    write_to_order_logs(message)
                    save_state(positions_state)
            elif ltp >= t4:
                tgt4_lots = params["Tgt4Lots"]
                if tgt4_lots > 0 and remaining_lots >= tgt4_lots:
                    place_sell_order(params["FyresSymbol"], tgt4_lots, ltp)
                    pos_state['remaining_lots'] -= tgt4_lots
                    pos_state['t4_hit'] = True
                    pos_state['position_state'] = 't4_hit'
                    message = f"[T4 HIT] {params['Symbol']} at {ltp:.2f}, Exited: {tgt4_lots} lots, Remaining: {pos_state['remaining_lots']}"
                    print(message)
                    write_to_order_logs(message)
                    save_state(positions_state)
        
        elif position_state == 't4_hit':
            # Check SL4 only
            if ltp <= sl4:
                # Exit all remaining lots
                if remaining_lots > 0:
                    place_sell_order(params["FyresSymbol"], remaining_lots, ltp)
                    pos_state['exited_today'] = True
                    pos_state['position_state'] = 'exited_sl4'
                    message = f"[EXIT - SL4] {params['Symbol']} at {ltp:.2f}, Lots: {remaining_lots}"
                    print(message)
                    write_to_order_logs(message)
                    save_state(positions_state)
    
    except Exception as e:
        print(f"Error monitoring entry/exit for {params.get('Symbol', 'unknown')}: {e}")
        traceback.print_exc()

def main_strategy():
    """
    Main strategy function that handles both signal detection and entry/exit monitoring
    """
    try:
        global result_dict
        positions_state = load_state()
        
        # Update LTP data
        UpdateData()
        
        now = datetime.datetime.now()
        
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
                next_check_time = normalized_time + datetime.timedelta(minutes=timeframe)
                pos_state['next_check_time'] = next_check_time.isoformat()
                save_state(positions_state)
            
            # Convert string back to datetime
            if isinstance(next_check_time, str):
                next_check_time = datetime.datetime.fromisoformat(next_check_time)
            
            # Check if it's time to fetch historical data
            if now >= next_check_time:
                # Check for signal
                signal_detected = check_signal_for_symbol(unique_key, params, positions_state)
                
                # Update next check time
                normalized_time = normalize_time_to_timeframe(now, timeframe)
                next_check_time = normalized_time + datetime.timedelta(minutes=timeframe)
                pos_state['next_check_time'] = next_check_time.isoformat()
                save_state(positions_state)
        
        # Phase 2: Monitor entry/exit for symbols with signals (every second)
        for unique_key, params in result_dict.items():
            monitor_entry_exit(unique_key, params, positions_state)
            
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
    
    # Load and check state - reset if from different day
    positions_state = load_state()
    today = datetime.datetime.now().date().isoformat()
    state_date = None
    try:
        with open('state.json', 'r') as f:
            state = json.load(f)
            state_date = state.get('date')
    except:
        pass
    
    # Reset exited_today flags if it's a new day
    # If position was exited yesterday, allow fresh pattern check today
    # If position is still open, keep monitoring it
    if state_date != today:
        for key in positions_state:
            pos_state = positions_state[key]
            # If exited yesterday, reset everything for fresh start
            if pos_state.get('exited_today'):
                positions_state[key] = {}  # Clear state for fresh pattern check
            else:
                # Keep monitoring open positions, just reset exited_today flag
                pos_state['exited_today'] = False
        save_state(positions_state)
        print(f"[STATE] New day detected. Resetting exited positions. Open positions will continue to be monitored.")

    # Initialize Market Data API
    fyres_websocket(FyerSymbolList)
    time.sleep(5)
    
    print(f"[STARTUP] Strategy initialized at {datetime.datetime.now()}")
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
         
    
