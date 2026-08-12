# ATM-001 — Withdraw Cash at an ATM

## Actors

* Cardholder  
* ATM  
* Financial Institution

## Context

This procedure describes a cardholder withdrawing cash from an automated teller machine (ATM) using a debit card and personal identification number (PIN).

## Preconditions

* Cardholder has an active debit card.  
* Cardholder knows the card PIN.  
* ATM is available and has sufficient cash to operate.  
* Cardholder has access to the selected account.

## Outcome

The cardholder receives the requested cash, retrieves the debit card, and the Financial Institution records the withdrawal. If the transaction cannot be completed, the ATM provides an appropriate message without dispensing cash.

Version

* ATM Standard Procedure — 2026-08-12 — v1.0

## Main Path

1. **Cardholder** inserts the debit card into the **ATM**.  
2. **ATM** reads the card and prompts the **Cardholder** to enter the PIN.  
3. **Cardholder** enters the PIN.  
4. **ATM** verifies the PIN with the **Financial Institution** \[a\].  
5. **ATM** displays transaction options to the **Cardholder**.  
6. **Cardholder** selects a cash withdrawal and enters the requested amount.  
7. **ATM** verifies with the **Financial Institution** that the account has sufficient available funds.  
8. **ATM** debits the selected account through the **Financial Institution**.  
9. **ATM** dispenses the requested cash.  
10. **ATM** returns the debit card and offers a receipt to the **Cardholder**.  
11. **Cardholder** takes the cash and debit card, and takes the receipt if requested.

## Options from main path:

### Option A — PIN Is Incorrect

Trigger: The ATM reports that the entered PIN is incorrect.

1. ATM informs the Cardholder that the PIN could not be verified.  
2. ATM permits another PIN entry when the retry limit has not been reached.  
3. If the retry limit is reached, ATM retains or returns the card according to the Financial Institution policy and ends the transaction \[a\].

### Option B — Account Has Insufficient Funds

Trigger: The Financial Institution reports that the selected account does not have sufficient available funds.

1. ATM informs the Cardholder that the requested amount cannot be withdrawn.  
2. ATM prompts the Cardholder to enter a smaller amount or cancel the transaction.  
3. If the Cardholder cancels, ATM returns the card and ends the transaction without dispensing cash.

### Option C — Cardholder Cancels the Transaction

Trigger: The Cardholder selects cancel before cash is dispensed.

1. ATM cancels the transaction before debiting the account.  
2. ATM returns the debit card.  
3. Cardholder retrieves the debit card.

## Notes

\[a\] PIN retry limits and card-retention behavior are set by the Financial Institution and may differ by card issuer.

\[ end \]
