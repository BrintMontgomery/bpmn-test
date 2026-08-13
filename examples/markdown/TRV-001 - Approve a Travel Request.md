# TRV-001 - Approve a Travel Request

## Actors

* Travel Approver  
* Requestor  
* Travel Request System

## Context

This procedure describes how a Travel Approver reviews and approves a travel request that is awaiting the approver's signature in the Travel Request System.

## Preconditions

* The Travel Approver has received the travel-request link by email.  
* The Travel Approver has access to the Travel Request System.  
* The travel request is awaiting the Travel Approver's signature.  
* The Travel Approver uses Microsoft Edge and has disabled its pop-up blocker for the Travel Request System.  

## Outcome

The Travel Request System records the Travel Approver's approval, and the Travel Approver can confirm that the request is approved and continuing through the approval process.

Version

* Travel Request Approval Procedure - 2026-08-13 - v1.0  

## Main Path

1. **Travel Approver** opens the travel-request link from the email in Microsoft Edge.  
2. **Travel Request System** displays the home page to the **Travel Approver**.  
3. **Travel Approver** selects Requests.  
4. **Travel Request System** displays the Travel Approver's request list.  
5. **Travel Approver** selects Details for the travel request awaiting signature.  
6. **Travel Request System** displays the travel request for the **Travel Approver**.  
7. **Travel Approver** moves to the second page of the travel request.  
8. **Travel Request System** displays the approval button at the bottom of the second page.  
9. **Travel Approver** selects the approval button.  
10. **Travel Request System** records the approval and updates the request status.  
11. **Travel Approver** returns to Requests and verifies that the travel request shows as approved \[a\].  

## Options from main path:

### Option A - Approval Button Is Not Displayed

Trigger: The Travel Approver cannot see the approval button after opening the travel request.

1. Travel Approver closes the travel-request window.  
2. Travel Approver opens the Approval Worklist in the Travel Request System.  
3. Travel Approver disables the Microsoft Edge pop-up blocker for the Travel Request System.  
4. Travel Approver opens the travel request from the Approval Worklist.  
5. Travel Approver moves to the second page and selects the approval button.

## Notes

\[a\] Hovering over the request in the request list may display the approval time and confirm that the approval was recorded.

\[ end \]
