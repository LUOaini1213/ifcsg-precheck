const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {matches, toCSV, download} = require('../src/ifcsg_precheck/report_assets/review.js');
const record = {kind:'finding',agency:'Demo A; Demo B',severity:'warning',status:'unit-unverified',guid:'ABC',property:'P.Width',detail:'IfcReal: unknown source'};
test('filters combine agency, severity, status, GlobalId and property without changing input', () => {
  const original = structuredClone(record);
  assert.ok(matches(record, {agency:'Demo B',severity:'warning',status:'unit-unverified',guid:'bc',property:'width'}));
  for (const bad of [{agency:'Demo'}, {severity:'error'}, {status:'verified'}, {guid:'XYZ'}, {property:'Depth'}]) {
    assert.equal(matches(record, bad), false);
  }
  assert.deepEqual(record, original);
});
test('CSV quotes delimiters and neutralizes spreadsheet formulas while JSON identities stay original', () => {
  const hostile = {...record, guid:'=HYPERLINK("bad")',property:'\t@SUM(A1)',detail:'comma, quote"\nnew line'};
  const csv = toCSV([hostile]);
  assert.ok(csv.includes('"\'=HYPERLINK(""bad"")"'));
  assert.ok(csv.includes('"\'\t@SUM(A1)"'));
  assert.ok(csv.includes('"comma, quote""\nnew line"'));
  assert.equal(hostile.guid, '=HYPERLINK("bad")');
});
test('download removes the anchor and schedules owned URL revocation even if clicking fails', () => {
  let removed = 0, revoked = [];
  const fakeURL = {createObjectURL:()=>'blob:owned',revokeObjectURL:url=>revoked.push(url)};
  const scheduled = [];
  const sandbox = {module:{exports:{}},setTimeout:callback=>scheduled.push(callback)};
  vm.runInNewContext(fs.readFileSync(require.resolve('../src/ifcsg_precheck/report_assets/review.js'),'utf8'), sandbox);
  const error = new Error('blocked click');
  const document = {createElement:()=>({click:()=>{throw error;},remove:()=>removed++}),body:{append:()=>{}}};
  assert.throws(()=>sandbox.module.exports.download(document,fakeURL,Blob,'review.json','application/json','{}'), e=>e===error);
  assert.equal(removed,1); assert.equal(scheduled.length,1);
  scheduled[0](); assert.deepEqual(revoked,['blob:owned']);
});
test('actual report browser controller hides matching rows, keeps complete JSON and exports visible CSV', () => {
  const data = {report:{summary:{errors:2}},review_records:[record,{...record,guid:'XYZ',agency:'Demo C',severity:'error',status:'needs-correction'},
    {...record,kind:'unit',severity:'evidence',evidence:{status:'unverified',measure_type:'IfcReal'}}]};
  const elements = {};
  function element(value='') {return {value,textContent:'',listeners:{},addEventListener(type,fn){this.listeners[type]=fn;}};}
  for (const key of ['agency','severity','status','guid','property']) elements['filter-'+key]=element();
  for (const id of ['review-filters','review-visible','download-json','download-csv']) elements[id]=element();
  elements['review-data']={textContent:JSON.stringify(data)};
  const rows=[{},{},{}], counts=[{dataset:{count:'finding'},textContent:''},{dataset:{count:'unit'},textContent:''}];
  const downloads=[], timers=[];
  const URL={createObjectURL:blob=>{downloads.push(blob);return 'blob:export';},revokeObjectURL:()=>{}};
  const document={getElementById:id=>elements[id],querySelectorAll:selector=>selector.includes('tr[')?rows:counts,
    createElement:()=>({click(){},remove(){}}),body:{append(){}}};
  vm.runInNewContext(fs.readFileSync(require.resolve('../src/ifcsg_precheck/report_assets/review.js'),'utf8'),
    {document,URL,Blob,setTimeout:fn=>timers.push(fn)});
  assert.equal(counts[0].textContent,'(2 of 2 shown)');
  elements['filter-status'].value='unit-unverified'; elements['filter-status'].listeners.input();
  assert.deepEqual(rows.map(row=>row.hidden),[false,true,false]);
  assert.equal(counts[0].textContent,'(1 of 2 shown)');
  assert.equal(counts[1].textContent,'(1 of 1 shown)');
  elements['filter-status'].value='';
  elements['filter-guid'].value='ABC'; elements['filter-guid'].listeners.input();
  assert.deepEqual(rows.map(row=>row.hidden),[false,true,false]);
  assert.equal(counts[0].textContent,'(1 of 2 shown)');
  elements['download-json'].listeners.click(); elements['download-csv'].listeners.click();
  return Promise.all(downloads.map(blob=>blob.text())).then(([json,csv])=>{
    assert.deepEqual(JSON.parse(json),data); assert.ok(csv.includes('ABC')); assert.ok(!csv.includes('XYZ'));
    elements['filter-guid'].value=''; elements['review-filters'].listeners.reset(); timers.at(-1)();
    assert.deepEqual(rows.map(row=>row.hidden),[false,false,false]);
  });
});
