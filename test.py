trades = [('buy', 16950.0, 0.05), ('buy', 16925.0, 0.05), ('sell', 16950.0, 0.05)]
J = 10000000000


print(trades)

fee = float('0.0002')
step = 25
aFee = 0

matcher = trades.copy()
total = 0

while len(matcher)>0:

    i1 = matcher[0]
    aSide = i1[0] # buy or sell
    aOpposite = 'sell' if aSide == 'buy' else 'buy'

    # lets look for corresponding opposite order
    matcher.remove(i1)
    for i2 in matcher:
        if i2 == (aOpposite,i1[1] + step,i1[2]):
            total += abs(int(i2[1] * J) - int(i1[1] * J)) * i2[2]
            # remove fee
            aFee = int(i2[1] * i2[2] * fee * J)
            aFee += int(i1[1] * i1[2] * fee * J)
            total -= aFee

            matcher.remove(i2)
            break

print(f'Total profit 💰 {total/J}')