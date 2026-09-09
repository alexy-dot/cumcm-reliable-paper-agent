import fs from 'node:fs/promises';
import path from 'node:path';
import {FileBlob, SpreadsheetFile} from '@oai/artifact-tool';

const run=path.resolve(process.argv[2]);
const mode=process.argv[3] ?? 'preview';
const files=await fs.readdir(path.join(run,'sources'));
const out=path.join(run,'artifacts','submission');
const previews=path.join(run,'tmp','workbooks');
await fs.mkdir(previews,{recursive:true});
if(mode==='fill') await fs.mkdir(out,{recursive:true});
const plans=mode==='fill'?JSON.parse(await fs.readFile(path.join(run,'artifacts','plans.json'),'utf8')):null;
const facts=mode==='fill'?JSON.parse(await fs.readFile(path.join(run,'artifacts','facts.json'),'utf8')):null;
for(const tag of ['A','B']) {
  const name=files.find(n=>n.includes('附件'+tag));
  const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(run,'sources',name)));
  for(let q=2;q<=4;q++) {
    const sheetName=`问题${q}的${tag==='A'?'订购':'转运'}方案结果`;
    const sheet=wb.worksheets.getItem(sheetName);
    if(mode==='preview') {
      const image=await wb.render({sheetName,range:'A1:J12',scale:1.5,format:'png'});
      await fs.writeFile(path.join(previews,`${tag}-Q${q}-before.png`),new Uint8Array(await image.arrayBuffer()));
      console.log((await wb.inspect({kind:'region',sheetId:sheetName,range:'A5:J9',maxChars:1200})).ndjson);
      continue;
    }
    const ids=sheet.getRange('A1:A409').values.flat();
    const start=ids.indexOf(facts.ids[0]);
    if(start<0 || !facts.ids.every((id,i)=>ids[start+i]===id)) throw new Error('supplier row identities differ');
    const data=facts.ids.map((_,i)=>tag==='A'
      ?plans['Q'+q].orders.map(week=>week[i]>1e-8?week[i]:null)
      :plans['Q'+q].shipments.flatMap(week=>week[i].map(v=>v>1e-8?v:null)));
    const writable=sheet.getRangeByIndexes(start,1,402,tag==='A'?24:192);
    writable.values=data;
    writable.setNumberFormat('0.000');
    const targetRow=start+plans['Q'+q].orders[0].findIndex(v=>v>1e-6)+1;
    const image=await wb.render({sheetName,range:`A${Math.max(5,targetRow-1)}:J${targetRow+6}`,scale:1.5,format:'png'});
    await fs.writeFile(path.join(previews,`${tag}-Q${q}-after.png`),new Uint8Array(await image.arrayBuffer()));
    console.log((await wb.inspect({kind:'region',sheetId:sheetName,range:`A${targetRow}:J${targetRow+2}`,maxChars:1200})).ndjson);
  }
  if(mode==='fill') {
    console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!',options:{useRegex:true,maxResults:20},maxChars:1600})).ndjson);
    const book=await SpreadsheetFile.exportXlsx(wb);
    await book.save(path.join(out,name.slice(name.indexOf('附件'))));
  }
}
