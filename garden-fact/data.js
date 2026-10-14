const names={"D19":"Limelight","D17":"Candlelight","D15":"Skyfall","D13":"Wim’s Red","D11":"Bee Green","D9":"Wim’s Red","D3":"Сакура","D2":"R. impeditum","D1":"Шизофрагма","C17":"Bee Green","C15":"Гортензия","C9":"Blue Bird","B17":"Blue Ball","B7":"Blue Bird","B1":"Клён","C4":"Cypripedium reginae","D5":"Cypripedium kentuckiense × parviflorum","D4":"Cyclamen coum ‘Silver Leaf Alba’","C2":"Cyclamen coum ‘Christmas Tree Leaf Alba’","C3":"Asplenium trichomanes"};

const pine=new Set([...Array.from({length:18},(_,i)=>'A'+(i+1)),...Array.from({length:8},(_,i)=>'B'+(i+8)),'B2','B3',...Array.from({length:5},(_,i)=>'C'+(i+10)),'C2']);

const bush=new Set(['D18','D16','D14','D12','D10','D8','D7','D6','D5','D4','C18','C16','C8','C7','C6','C5','C4','C3','B16','B6','B5','B4']);

pine.add('C1');

// Confirmed plantings 2026-10-14. C2/C3 is one cyclamen on the cell boundary.
const confirmedPlantings20261014=[{"name":"Cypripedium reginae","coord":"C4","count":1},{"name":"Cypripedium kentuckiense × parviflorum","coord":"D5","count":1},{"name":"Cyclamen coum ‘Silver Leaf Alba’","coord":"D4","count":1},{"name":"Cyclamen coum ‘Christmas Tree Leaf Alba’","coord":"C2/C3","count":1},{"name":"Asplenium trichomanes","coord":"C3","count":1}];
