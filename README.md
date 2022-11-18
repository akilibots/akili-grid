# Welcome to akili-grid!

### After the FTX saga I'm moving 100% defi - so, reprogramming all my bots to work exclusively with dydx

[![Telegram](https://badges.aleen42.com/src/telegram.svg)](https://t.me/+9F0CZj8emLc2YTY0)

Jambo! and welcome! akiligrid is a grid bot that uses the grid strategy to trade crypto currencies. The word **akili** means brain or mind in Swahili. The objective here is to make it the most intelligent grid bot in existence that has as many advanced features as possible, but which at the same time can be used by your typical crypto trader with basic grid bot experience

This, as with all projects was born out of frustration on the lack of features with "commercial" bots out there. They always missed that little tweak that in my mind would make things a lot more better, and hopefully profitable.

Let's get the usual out of the way...

***DISCLAIMER

This software is for educational purposes only. Do not risk money which you are afraid to lose. USE THE SOFTWARE AT YOUR OWN RISK. THE AUTHORS AND ALL AFFILIATES ASSUME NO RESPONSIBILITY FOR YOUR TRADING RESULTS.***

  

## Instructions
### Installing & Running

 1. Clone the repo 
 2. Install the dependencies by typing 
`pip install -r requirements.txt` 
 3. Create your strategy. This will create a subfolder strategies with your strategy data in as sub folder matching your strategy name. To create a new strategy, type
`python create.py mystrategy`
4. Configure your strategy by editing the strategy.ini file in your strategy folder.
5. Run your strategy by typing
`python run.py mystrategy`
6. akiligrid will create a log in your strategy folder called log.txt or update you via telegram if you set it up.

I have been testing with FTX so I recommend it. If you do not have an account please use my affiliate link below. You get a discount on fees and I get a percentage so its a win win. Thank you.

After the FTX saga, I'm going defi so here's my affiliate link to dydx https://dydx.exchange/r/JUDCLWBC
I'm also re-programming my bots to use dydx exclusively

For instructions on how to get your private keys for this bot, take a look here https://twitter.com/ChrisJangita/status/1593532341669896193

More affiliate links to come. 
 
I'll be testing on more exchanges soon. So far so good and the grid works as it should. There some little things I still need to iron out such as
 1. No errors messages. It just throws python exceptions.
 2. If you loose connection to the exchange, the script ends. It should be able to save state so you can pause, resume or restart if an exchange disconnect occurs.
 3. If there is a large price rise that takes out more than one order above the current price ,the grid gets confused it scans orders from the bottom up. This can be mitigated by having one open order above. This doesn't happen if the price drops.
 4. Need to Dockerise it so a user doesn't have to mess around with python and screen if running it off a server.
 5. Implement a way to control the grid and change parameters on the fly using telegram, keypresses, or an open port.
