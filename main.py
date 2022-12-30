from scipy.stats import norm
from datetime import timedelta
import numpy as np
# This is meant to be run on QuantConnect
# TODO: fix liabilities clearing and insufficient funds
class IronCondorAlgorithm(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2019, 11, 1)
        self.SetEndDate(2020, 11, 1)
        self.SetCash(5000)
        self.Debug('Starting Cash: ' + str(self.Portfolio.Cash))
        # Add equities
        self.equity = [x for x in self.ActiveSecurities]
        self.stock_list = ["SPY", "VCR", "SLY", "EEM", "XLP", "ARKK", "XLY"]
        for symbol in stock_list:
          self.equity.append(self.AddEquity(symbol, Resolution.Minute))
        symbols = []
        for x in self.stock_list:
            symbols.append(Symbol.Create(x, SecurityType.Equity, Market.USA))
        self.SetUniverseSelection(ManualUniverseSelectionModel(symbols))
        self.options = []
        # Create an array of options for each symbol
        for x in self.equity:
            self.options.append(self.AddOption(x.Symbol, Resolution.Minute))
        self.condor_list = []
        # Create symbol array
        # self.symbols = [x for x.Symbol in self.options]
        # Specify universe function
        for x in self.options:
            x.SetFilter(self.UniverseFunc)
        self.SetBenchmark("SPY")
        self.counter = 0
        self.liabilities = []
        self.SetWarmup(1)
        # Set trading intervals
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.AfterMarketOpen("SPY", 1), self.TradeOptions)
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(12, 0), self.TradeOptions)
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.BeforeMarketClose("SPY", 10), self.TradeOptions)
        # self.Schedule.On(self.OptionPositionAssigned, self.Wings)

        
    def OnData(self, slice):
        self.most_recent_slice = slice

    def TradeOptions(self):
        # If there are undelying assets in portfolio at expiration, liquidate the stocks in order to roll into new contracts
        self.Debug(str(x for x in self.Portfolio))
        #This is a problem; it needs to be taylored to each option
        if self.Portfolio.Invested:
            self.AdjustOptions()
        elif self.Time.hour != 0 and self.Time.minute != 0: 
            # List of optionchains for each security
            self.AddToPortfolio()
            self.liabilities.clear()
    
    def CloseCondor(self, options_list):
        # self.Debug("CCC")
        for row in range(len(self.liabilities)):
            # If the option's symbols match
            if self.liabilities[row][0] is options_list[3].Symbol:
                self.liabilities.pop(row)
        for i in range(3):
            self.Liquidate(options_list[i].Symbol)
        if not self.Portfolio.Invested:
            self.liabilities.clear()

    def AdjustOptions(self):
        # self.Debug("Portfolio.Invested Called " + str(self.Time))
        # condor list: otm_call, otm_call_higher, otm_put, otm_put_lower, netPremium
        for x in self.condor_list:
            days_to_expiry = abs(x[0].Expiry - self.Time).days
            # if this condor expires in 25+ days, leave it
            if days_to_expiry > 25:
                continue
            elif days_to_expiry < 3.75:
                self.CloseCondor(x)
            
            # OTM Check
            otm = True
            # c for contract
            for c in range(3):
                if x[c].Right == 1: # put check
                    if x[c].UnderlyingLastPrice < x[c].Strike:
                        otm = False
                else: # call check
                    if x[c].UnderlyingLastPrice > x[c].Strike:
                        otm = False
            # If Condor is in the head region, close
            if otm:
                self.CloseCondor(x)
            # Exit at 20% profit, checking, respectively, if its in the diagonal of the put and call
            if x[3].UnderlyingLastPrice > x[3].Strike and x[4] - (x[2].Strike - x[3].UnderlyingLastPrice) > 1.2 * x[5]:
                self.CloseCondor(x)
            elif (x[1].UnderlyingLastPrice < x[1].Strike) and (x[4] - (x[1].UnderlyingLastPrice - x[0].Strike) > 1.2 * x[5]):
                self.CloseCondor(x)

        #Clean out actual stocks
        for ticker in self.stock_list:
            self.SetHoldings(ticker, 0)

    def AddToPortfolio(self):
        for i in self.most_recent_slice.OptionChains:
            # self.Debug("Iteration Number " + str(self.counter))
            chain = i.Value
            contract_list = [x for x in chain]
            # if there is no optionchain or no contracts in this optionchain, pass the instance
            if (self.most_recent_slice.OptionChains.Count == 0) or (len(contract_list) == 0): 
                continue   
            # sorted the optionchain by expiration date and choose the furthest date
            expiry = sorted(chain,key = lambda x: x.Expiry)[-1].Expiry
            # filter the call and put options from the contracts
            put = [i for i in chain if i.Expiry == expiry and i.Right == 1]
            # self.Debug("Puts: " + str(x.Strike for x in put))
            if len(put) > 2:
                put_contracts = sorted(put,key = lambda x: x.Strike)
            else:
                continue
            highest_put_strike = put_contracts[len(put_contracts) - 1].Strike
            
            call = [i for i in chain if i.Expiry == expiry and i.Right == 0 and i.Strike > put[0].UnderlyingLastPrice]
            if len(call) > 2:
                call_contracts = sorted(call,key = lambda x: x.Strike) 
            else:
                continue
            
            # sorted the contracts according to their strike prices 
            # self.Debug(put_contracts[len(put_contracts) - 1].UnderlyingSymbol.Value + ' ' + str(len(put_contracts)) + ' ' + str(len(call_contracts)))
            # self.Debug('price= ' + str(put_contracts[0].UnderlyingLastPrice) + 'PUTS: ' + ' '.join(str([x.Strike for x in put_contracts])))
            put_contracts = [i for i in put if i.Strike < i.UnderlyingLastPrice]
            # self.Debug('CALLS: ' + ' '.join([x.Strike for x in call_contracts]))

            put_contracts = sorted(put,key = lambda x: x.Strike)    
            if len(call_contracts) == 0 or len(put_contracts) == 0 : continue

            otm_put_lower = put_contracts[0]
            otm_put = put_contracts[len(put_contracts) - 1]
            try:
                otm_call = call_contracts[-10]
            except IndexError:
                otm_call = call_contracts[-1 * len(call_contracts)]
                self.Debug("otm_call Index Error")
            try:
                otm_call_higher = call_contracts[-1]
            except IndexError:
                otm_call_higher = call_contracts[1]
                self.Debug("otm_call_higher Index Error")
                
            # self.Debug('Lower Put ' + str(otm_put_lower.Strike) + 'Higher Put ' + str(otm_put.Strike) + 'Lower Call: ' + str(otm_call.Strike) + 'Higher Call' + str(otm_call_higher.Strike))
            expiry = otm_call_higher.Expiry
            # if there are no securities in portfolio, trade the options 
            totalPrice = sum([x.AskPrice for x in [otm_call_higher, otm_put_lower]]) - otm_put.BidPrice - otm_call.BidPrice + 100*otm_call.UnderlyingLastPrice
            maximumLoss = 100 * (otm_put.Strike - otm_put_lower.Strike) + otm_put.BidPrice + otm_call.BidPrice - otm_put_lower.BidPrice - otm_call_higher.BidPrice
            total_liabilities = 0
            for row in range(len(self.liabilities)):
                total_liabilities += self.liabilities[row][1]
            # self.Debug("Liabilities: " + str(total_liabilities))
            # self.Debug("Cash: " + str(self.Portfolio.Cash))
            if total_liabilities + maximumLoss < self.Portfolio.Cash:
                # self.Debug("Passed Enough Cash Test. Cash: " + str(self.Portfolio.Cash))
                # self.Debug("Option Total Pricetag: " + str(totalPrice))
                self.Buy(otm_put_lower.Symbol ,1)
                self.Sell(otm_put.Symbol ,1)
                self.Sell(otm_call.Symbol ,1)
                self.Buy(otm_call_higher.Symbol ,1)
                self.liabilities.append([otm_put_lower.Symbol, maximumLoss])
                netPremium = otm_put.BidPrice + otm_call.BidPrice - otm_put_lower.BidPrice - otm_call_higher.BidPrice
                self.condor_list.append([otm_call, otm_call_higher, otm_put, otm_put_lower, netPremium, totalPrice])

            self.counter += 1
            
    def Wings():
        if True:
            self.ExerciseOption(contract_symbol, quantity)

    def ExpectedValue(x):
        # What will q be? 100? (that is assumed here)
        mu = x[0].UnderlyingLastPrice
        sigma = x[0].ImpliedVolatility
        C = x[1].BidPrice + x[2].BidPrice - x[0].BidPrice - x[3].BidPrice
        y = []
        y[0] = norm.cdf(x[0].Strike, mu, sigma) * -100 * (x[1].Strike - x[0].Strike)
        Ptwo = norm.cdf(x[1].Strike, mu, sigma) - norm.cdf(x[0].Strike, mu, sigma)
        y[1] = Ptwo * -100 
        y[2] = 2
        y[3] = 3
        y[4] = 4
        
    def OnOrderEvent(self, orderEvent):
        self.Debug(str(orderEvent))

    def UniverseFunc(self, universe):
        return universe.IncludeWeeklys().Strikes(-15, 15).Expiration(timedelta(35), timedelta(50))
