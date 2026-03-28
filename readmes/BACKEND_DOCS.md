SYSTEM OVERVIEW :

-Client
- ↓
-Session Service (timer + state)
- ↓
-Question Service (select + lock question)
- ↓
-Collection Phase (Benji → structured design)
- ↓
-Evaluation Pipeline (hint/review)
- ↓
-AI Evaluation Service
- ↓
-Response (hint / score / next step)
    


KEY COMPONENTS-

When a user wants to begin we will start a SESSION, sessions are 10 minutes. hint will stop timer and resume after hint is generated, review will end timer.   

-QUESTION BANK
  - contains all archetecures
  - must be able to be read by ai
  - consistent with format
  - 5 for testing 
  - randomizer that sends one to the front end, keeps it in mind the whole session so we can acess the correct solution

DURING SESSION:


-COLLECTION PHASE(handled by benji) :
  - input: periodicly taken images and constant audio
  - Output: a mapped out archetecture in the same fomart as the one in the question bank 


-REVIEW OR HINT (sends user map and solution map for eval.) :
 - hint 
    - gives a suggestion communicates that to front end for display.

 -review
  -gives a grade and reveals improvements to make displayed on front end
  -decides based on grade if it will ask follow up or ask for implemented correction 




