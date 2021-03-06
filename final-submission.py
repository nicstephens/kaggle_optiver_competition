# This Python 3 environment comes with many helpful analytics libraries installed
# It is defined by the kaggle/python Docker image: https://github.com/kaggle/docker-python
# For example, here's several helpful packages to load

import numpy as np # linear algebra
import pandas as pd # data processing, CSV file I/O (e.g. pd.read_csv)

# Input data files are available in the read-only "../input/" directory
# For example, running this (by clicking run or pressing Shift+Enter) will list all files under the input directory

import os
for dirname, _, filenames in os.walk('/kaggle/input'):
    for filename in filenames:
        print(os.path.join(dirname, filename))

# You can write up to 20GB to the current directory (/kaggle/working/) that gets preserved as output when you create a version using "Save & Run All" 
# You can also write temporary files to /kaggle/temp/, but they won't be saved outside of the current session
import os
import glob
import pandas as pd
pd.options.mode.chained_assignment = None
from sklearn.linear_model import LinearRegression
import time 
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.compose import ColumnTransformer
#from sklearn.neural_network import MLPRegressor
from xgboost import XGBRegressor

start = time.time()

 
def get_book_df(train_test, stock_id):
    target_path = '/kaggle/input/optiver-realized-volatility-prediction/book_' + train_test + '.parquet/stock_id=' + str(stock_id) +'/' 
    df = pd.read_parquet(target_path)
    df['mid'] = (df['bid_price1']+df['ask_price1'])/2
    df['wap'] =(df['bid_price1'] * df['ask_size1']+df['ask_price1'] * df['bid_size1'])  / (
                                      df['bid_size1']+ df['ask_size1'])
    
    return df
    


def get_trade_df(train_test, stock_id):
    target_path = '/kaggle/input/optiver-realized-volatility-prediction/trade_' + train_test + '.parquet/stock_id=' + str(stock_id) +'/'
    df1 = pd.read_parquet(target_path)
    return df1

def log_return(list_stock_prices):
    return np.log(list_stock_prices).diff()

def logged_vol(series_log_return):
        return np.log1p((np.sqrt(np.sum(series_log_return**2))))

def bipower_variation(series_log_return):
    u = np.sqrt(np.pi / 2) ** -2
    pre_log = u * sum([abs(f) * abs(p) for f, p in zip(series_log_return[2:], series_log_return[1:])])
    return np.log1p(pre_log)

def filter_(raw_df, time_id):
    
    df = raw_df.loc[raw_df['time_id'] == time_id]
    #df['seconds_in_bucket'] = df['seconds_in_bucket'] - df['seconds_in_bucket'].min()
    return df

        
def filled_book_trade_df(book_df, trade_df, time_id):
    book_df = filter_(book_df, time_id).set_index('seconds_in_bucket')
    trade_df = filter_(trade_df, time_id).set_index('seconds_in_bucket')
    df = pd.concat([book_df, trade_df], axis=1)
    df['time_id'] = time_id
    df[['bid_price1','ask_price1','bid_price2','ask_price2','bid_size1','ask_size1','bid_size2','ask_size2', 'wap']] = df[['bid_price1','ask_price1','bid_price2','ask_price2','bid_size1','ask_size1','bid_size2','ask_size2', 'wap']].fillna(method = 'ffill')
    df['log_return'] = log_return(df['wap'])
    df['log_return'] = df['log_return'].fillna(0)
    df[['size', 'order_count']] = df[['size', 'order_count']].fillna(0)
    df['price'] = df['price'].astype(float)
    df['price'] = df['price'].fillna(df['wap'])
    return df

def s_book_trade_df(book_df, trade_df, time_id):
    book_df = filter_(book_df, time_id).set_index('seconds_in_bucket')
    trade_df = filter_(trade_df, time_id).set_index('seconds_in_bucket')
    df = pd.concat([book_df, trade_df], axis=1)
    df['time_id'] = time_id
    df[['bid_price1','ask_price1','bid_price2','ask_price2','bid_size1','ask_size1','bid_size2','ask_size2', 'wap']] = df[['bid_price1','ask_price1','bid_price2','ask_price2','bid_size1','ask_size1','bid_size2','ask_size2', 'wap']].fillna(method = 'ffill')
    df['log_return'] = log_return(df['wap'])
    df['log_return'] = df['log_return'].fillna(0)
    df[['size', 'order_count']] = df[['size', 'order_count']].fillna(0)
    df['price'] = df['price'].astype(float)
    df['price'] = df['price'].fillna(df['wap'])
    return df

def depth(bid_or_ask_1, bid_or_ask_2, bid_or_ask_1_volume, bid_or_ask_2_volume):
    x = np.sum((np.multiply(bid_or_ask_2,bid_or_ask_2_volume)))
    y = np.sum((np.multiply(bid_or_ask_1,bid_or_ask_1_volume)))
    return np.log1p((x+y))

def slope(best_order, second_best_order, mid_price):
    return np.log1p(np.mean((best_order-second_best_order)/mid_price))

def trade_dist(series_trade_price,series_best_bid, series_best_ask):
    z = np.mean(series_trade_price/((series_best_ask+series_best_ask)/2))
    return z

#path_list = glob.glob('/kaggle/input/optiver-realized-volatility-prediction/book_test.parquet/*')

test_df = pd.read_csv('/kaggle/input/optiver-realized-volatility-prediction/test.csv')

stock_id_list = test_df['stock_id'].unique()
#stock_id_list = [0]
targets_df = pd.read_csv('/kaggle/input/optiver-realized-volatility-prediction/train.csv')

features = np.array([])
agg_targets = np.array([])
agg_index= np.array([])
agg_predictions = np.array([])
rescaled_agg_targets = np.array([])

startloop = time.time()


for stock_id in stock_id_list:
    
    ## retrieve data for training ##
    train_stock_book_df = get_book_df('train', stock_id)
    train_stock_trade_df = get_trade_df('train',stock_id)
    train_time_id_list = train_stock_book_df['time_id'].unique()
    train_stock_target_df = targets_df.loc[lambda df: df['stock_id'] == stock_id]

    
    ## initiate lists to fill with augmented/feature engineereed training data ##
    m_bid_1 = []
    m_bid_avg = []
    m_ask_1 = []
    m_ask_avg = []
    bid_depth_1 = []
    bid_depth_avg = []
    ask_depth_1 = []
    ask_depth_avg = []
    rv_1 = []
    rv_2 =[]
    bpv_1 = []
    bpv_2 = []
    targets = []
    index= []


    
    for train_time_id in train_time_id_list:
        
        raw = s_book_trade_df(train_stock_book_df, train_stock_trade_df, train_time_id)
        df1 = train_stock_target_df.loc[lambda df: df['time_id'] == train_time_id]
        
        t1_log_return = raw['log_return']
        t1_bid1 = raw['bid_price1']
        t1_bids2 = raw['bid_price2']
        t1_mid = raw['mid']
        t1_ask1 = raw['ask_price1']
        t1_ask2 = raw['ask_price2']
        t1_bid1_size = raw['bid_size1']
        t1_bid2_size = raw['bid_size2']
        t1_ask1_size = raw['ask_size1']
        t1_ask2_size = raw['ask_size2']
        t1_trade_price = raw['price']
        
        
      
        index.append(str(stock_id) + '-' + str(train_time_id))
        #m_bid_1.append(slope(t1_bid1.head(300), t1_bids2.head(300), t1_mid.head(300)))
        m_bid_avg.append(slope(t1_bid1, t1_bids2, t1_mid))
        #m_ask_1.append(slope(t1_ask1.head(300), t1_ask2.head(300), t1_mid.head(300)))
        m_ask_avg.append(slope(t1_ask1, t1_ask2, t1_mid))
        #bid_depth_1.append(depth(t1_bid1.head(300), t1_bids2.head(300), t1_bid1_size.head(300), t1_bid2_size.head(300)))
        bid_depth_avg.append(depth(t1_bid1, t1_bids2, t1_bid1_size, t1_bid2_size))
        #ask_depth_1.append(depth(t1_ask1_size.head(300), t1_ask2.head(300), t1_ask1_size.head(300), t1_ask1_size.head(300)))
        ask_depth_avg.append(depth(t1_ask1, t1_ask2, t1_ask1_size, t1_ask2_size))
        #rv_1.append(((logged_vol(t1_log_return.head(300)))))
        rv_2.append((logged_vol(t1_log_return)))
        bpv_1.append(trade_dist(t1_trade_price,t1_bid1, t1_ask1))
        bpv_2.append(bipower_variation(t1_log_return))
        targets.append(np.log1p(df1['target'].values[0]))
    
    ind_df = pd.DataFrame({#'m_bid_1': m_bid_1, 
                           'm_bid_avg': m_bid_avg, 
                           #'m_ask_1': m_ask_1, 
                           'm_ask_avg': m_ask_avg, 
                           #'bid_depth_1': bid_depth_1, 
                           'bid_depth_avg': bid_depth_avg, 
                           #'ask_depth_1': ask_depth_1, 
                           'ask_depth_avg': ask_depth_avg, 
                           #'rv_1' : rv_1, 
                           'rv_2': rv_2, 
                           'bpv_1' : bpv_1, 
                           'bpv_2' : bpv_2})
    

   ## put training features and targets into trainable structure ##                 
    dep_df = pd.DataFrame({'targets': targets})
    row_id_df = pd.DataFrame({'row_id': index})
    ind_np_train = ind_df.to_numpy()
    dep_np_train = dep_df.to_numpy()
    sample_size = int((ind_np_train.size)/7)
    
    ## fit XGBoost to the training data ##
    X = ind_np_train.reshape(sample_size,7)
    y = dep_np_train.reshape(sample_size).ravel()
    reg = XGBRegressor(max_depth = 3, eta = 0.15)
    reg.fit(X,y)
    
    ## retrieve data for testing ##
    test_stock_book_df = get_book_df('test', stock_id)
    test_stock_trade_df = get_trade_df('test',stock_id)
    #test_time_id_list = test_stock_book_df['time_id'].unique()
    test_time_id_list = test_stock_book_df['time_id'].unique()
    
    ## initiate lists tof ill with augmented/feature engineered test data ##
    ts_m_bid_1 = []
    ts_m_bid_avg = []
    ts_m_ask_1 = []
    ts_m_ask_avg = []
    ts_bid_depth_1 = []
    ts_bid_depth_avg = []
    ts_ask_depth_1 = []
    ts_ask_depth_avg = []
    ts_rv_1 = []
    ts_rv_2 =[]
    ts_bpv_1 = []
    ts_bpv_2 = []
    ts_targets = []
    ts_index= []
    
    for test_time_id in test_time_id_list:
        
        raw = s_book_trade_df(test_stock_book_df, test_stock_trade_df, test_time_id)
        #df1 = test_stock_target_df.loc[lambda df: df['time_id'] == test_time_id]
        
        t1_log_return = raw['log_return']
        t1_bid1 = raw['bid_price1']
        t1_bids2 = raw['bid_price2']
        t1_mid = raw['mid']
        t1_ask1 = raw['ask_price1']
        t1_ask2 = raw['ask_price2']
        t1_bid1_size = raw['bid_size1']
        t1_bid2_size = raw['bid_size2']
        t1_ask1_size = raw['ask_size1']
        t1_ask2_size = raw['ask_size2']
        t1_trade_price = raw['price']
        
      
        ts_index.append(str(stock_id) + '-' + str(test_time_id))
        #ts_m_bid_1.append(slope(t1_bid1.head(300), t1_bids2.head(300), t1_mid.head(300)))
        ts_m_bid_avg.append(slope(t1_bid1, t1_bids2, t1_mid))
        #ts_m_ask_1.append(slope(t1_ask1.head(300), t1_ask2.head(300), t1_mid.head(300)))
        ts_m_ask_avg.append(slope(t1_ask1, t1_ask2, t1_mid))
        #ts_bid_depth_1.append(depth(t1_bid1.head(300), t1_bids2.head(300), t1_bid1_size.head(300), t1_bid2_size.head(300)))
        ts_bid_depth_avg.append(depth(t1_bid1, t1_bids2, t1_bid1_size, t1_bid2_size))
        #ts_ask_depth_1.append(depth(t1_ask1_size.head(300), t1_ask2.head(300), t1_ask1_size.head(300), t1_ask1_size.head(300)))
        ts_ask_depth_avg.append(depth(t1_ask1, t1_ask2, t1_ask1_size, t1_ask2_size))
        #ts_rv_1.append(((logged_vol(t1_log_return.head(300)))))
        ts_rv_2.append((logged_vol(t1_log_return)))
        ts_bpv_1.append(trade_dist(t1_trade_price,t1_bid1, t1_ask1))
        ts_bpv_2.append(bipower_variation(t1_log_return))
 
    
    train_feat_df = pd.DataFrame({#'m_bid_1': ts_m_bid_1, 
                           'm_bid_avg': ts_m_bid_avg, 
                           #'m_ask_1': ts_m_ask_1, 
                           'm_ask_avg': ts_m_ask_avg, 
                           #'bid_depth_1': ts_bid_depth_1, 
                           'bid_depth_avg': ts_bid_depth_avg, 
                           #'ask_depth_1': ts_ask_depth_1, 
                           'ask_depth_avg': ts_ask_depth_avg, 
                           #'rv_1' : ts_rv_1, 
                           'rv_2': ts_rv_2, 
                           'dist' : ts_bpv_1, 
                           'bpv_2' : ts_bpv_2})
    
    
 
    
    ## put test features into structure that XGBoost can predict ##                     
    row_id_df = pd.DataFrame({'row_id': ts_index})
    feat_np_test = train_feat_df.to_numpy()
    agg_index = np.append(agg_index, ts_index)
    test_sample_size = int((feat_np_test.size)/7)
    
    ## make predcitions and save as pandas DataFrame##                  
    unscaled_pred = reg.predict(feat_np_test.reshape(test_sample_size, 7))
    #scaler.fit(dep_np_unscaled)
    scaled_pred = np.expm1(unscaled_pred.reshape(test_sample_size,1))
    agg_predictions = np.append(agg_predictions, scaled_pred)

end = time.time()

print (end-start)

pred_df = pd.DataFrame(agg_predictions, columns = ['target'])
row_id_df = pd.DataFrame(agg_index, columns = ['row_id'])
final_df = pd.concat([row_id_df, pred_df], axis = 1)
final_df.to_csv('submission.csv', index=False)
