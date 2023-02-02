# Welcome to akili-grid!

[![stability-beta](https://img.shields.io/badge/stability-beta-33bbff.svg)](https://github.com/mkenney/software-guides/blob/master/STABILITY-BADGES.md#beta)
[![Telegram](https://badges.aleen42.com/src/telegram.svg)](https://t.me/+9F0CZj8emLc2YTY0)

Jambo! and welcome! akiligrid is a grid bot that uses the grid strategy to trade crypto currencies. The word **akili** means brain or mind in Swahili. The objective here is to make it the most intelligent grid bot in existence that has as many advanced features as possible, but which at the same time can be used by your typical crypto trader with basic grid bot experience

This, as with all projects was born out of frustration on the lack of features with "commercial" bots out there. They always missed that little tweak that in my mind would make things a lot more better, and hopefully profitable.

Let's get the usual out of the way...

***DISCLAIMER

This software is for educational purposes only. Do not risk money which you are afraid to lose. USE THE SOFTWARE AT YOUR OWN RISK. THE AUTHORS AND ALL AFFILIATES ASSUME NO RESPONSIBILITY FOR YOUR TRADING RESULTS.***

  

## Instructions
### Installing & Running

1. Clone the repo 
2. Configure your strategy. Use the template in the /data/strategy.json file. 
3. Set your private keys in the data/tokens.json file. For instructions on how to get your private keys for this bot, take a look here https://twitter.com/ChrisJangita/status/1593531663597723648
3. Run your bot by typing in
`docker compose up -d`

The bot will send status messages via telegram if you set it up.

This has been extensively tested in dYdX and has run for a full month, generating $10M trading volume in Dec 2022 with no errors. If you do not have an account with dYdX please use my affiliate link https://dydx.exchange/r/JUDCLWBC . You get a discount on fees and I get a percentage so its a win win. Thank you.

More affiliate links to come. 
 
I'll don't know if I will eventually expand to other exchanges, but so far so good and the grid works as it should. There some little things I still need to iron out such as
 1. Fixed ✅ No errors messages. It just throws python exceptions.
 2. Fixed ✅ If you loose connection to the exchange, the script ends. It should be able to save state so you can pause, resume or restart if an exchange disconnect occurs.
 3. Fixed ✅ If there is a large price rise that takes out more than one order above the current price ,the grid gets confused it scans orders from the bottom up. This can be mitigated by having one open order above. This doesn't happen if the price drops.
 4. Fixed ✅ Need to Dockerise it so a user doesn't have to mess around with python and screen if running it off a server.
 5. Implement a way to control the grid and change parameters on the fly using telegram, keypresses, or an open port.
