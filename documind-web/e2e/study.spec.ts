import {test,expect} from '@playwright/test';

test.beforeEach(async({page})=>{
  let jobs=0;const items:unknown[]=[];
  const input={operation:'solve',expression:'2*x=8',variable:'x',domain:'real'};
  const source={id:'S1',pdf_id:1,page:2,filename:'study-notes.pdf',excerpt:'A source-linked method.'};
  const result={input,operation:'solve',result:'{4}',latex:'\\{4\\}',verified:true,checks:[{label:'Substitution into original equation',passed:true}],steps:['Solve 2*x=8.'],working_checks:[],assumptions:['Real domain.'],engine:'SymPy'};
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;const data=route.request().postDataJSON?.()||{};
    if(path==='/api/summarizer/workspaces')return route.fulfill({json:[{id:'browser-study',title:'Study examples',revision:1,updated:1,messages:[],documents:[{id:1,filename:'study-notes.pdf',status:'completed',page_count:3},{id:2,filename:'exam-fa.pdf',status:'completed',page_count:1}]}]});
    if(path.endsWith('/models'))return route.fulfill({json:{installed:['llama3.2:3b']}});
    if(path.includes('/study/papers/'))return route.fulfill({json:{questions:[{number:'1',text:'سؤال ۱. معادله را حل کنید.',pdf_id:2,page:1,marks:1,subparts:[]}],instructions:'',notice:'Review detected questions.'}});
    if(path.includes('/study/items/'))return route.fulfill({json:items});
    if(path.endsWith('/study/items')){items.push(data);return route.fulfill({json:{id:'saved-item',...data}});}
    if(path.endsWith('/solve'))return route.fulfill({json:result});
    if(path.endsWith('/study/jobs')){jobs++;return route.fulfill({json:{id:`study-job-${jobs}`}});}
    if(path.endsWith('/events')){
      const events=jobs===1?[
        {type:'metadata',interpretation:{math:input,missing:[],assumptions:[]},request_question:'Twice a number equals eight.',sources:[source]},
        {type:'text',content:'Review the translated input.'},
        {type:'done',metrics:{awaiting_interpretation:true,request_question:'Twice a number equals eight.'}},
      ]:[{type:'metadata',math:result,sources:[source]},{type:'text',content:'$$x=4$$\n\nThe method reference is [S1].'},{type:'done',metrics:{}}];
      return route.fulfill({contentType:'application/x-ndjson',body:events.map(e=>JSON.stringify(e)+'\n').join('')});
    }
    return route.fulfill({json:{}});
  });
  await page.goto('/study');
});

test('calculator renders mathematics and focuses its checked result',async({page})=>{
  await expect(page.getByRole('option',{name:'Study examples'})).toBeAttached();
  await page.getByLabel('Equation or expression').fill('2*x=8');
  await page.getByRole('button',{name:'Calculate & check'}).click();
  await expect(page.getByText('Listed calculation checks passed')).toBeVisible();
  await expect(page.getByRole('heading',{name:'Your working space'})).toBeFocused();
  await expect(page.locator('.solution-paper math').first()).toBeAttached();
  await page.getByRole('button',{name:'Revisit this problem'}).click();
  await expect(page.getByText('Saved to this workspace.')).toBeVisible();
});

test('Persian paper keeps references separate and renders its answer mathematics',async({page})=>{
  let payload:Record<string,unknown>={};
  await page.route('**/api/summarizer/study/exams/jobs',async route=>{payload=route.request().postDataJSON();await route.fulfill({json:{id:'persian-exam-job'}});});
  await page.route('**/api/summarizer/jobs/persian-exam-job/events',route=>route.fulfill({contentType:'application/x-ndjson',body:[{type:'question',number:'1',question:'معادله را حل کنید.',answer:'نتیجه:\n\n$$x=2$$\n\nروش حل در جزوه است. [S1]',status:'answered',sources:[{id:'S1',pdf_id:1,page:1,filename:'study-notes.pdf',excerpt:'روش حل'}]},{type:'done',metrics:{question_count:1,failed_questions:0,review_required:0}}].map(row=>JSON.stringify(row)+'\n').join('')}));
  await page.getByRole('button',{name:'Exam paper',exact:true}).click();
  await page.getByLabel('Exam PDF').selectOption('2');await page.getByLabel('Answer language').selectOption('fa');
  await page.getByRole('button',{name:'Answer this paper',exact:true}).click();
  await expect(page.getByText('Question 1 · Answer ready for review')).toBeVisible();
  expect(payload.reference_pdf_ids).toEqual([1]);expect(payload.exam_pdf_id).toBe(2);expect(payload.answer_language).toBe('fa');
  await expect(page.locator('.exam-answer .katex')).toBeVisible();await expect(page.locator('.exam-answer .answer')).toHaveAttribute('dir','auto');
});

test('mobile asks for interpretation review and keeps citations usable',async({page})=>{
  await page.setViewportSize({width:375,height:812});
  await page.getByLabel('Your question').fill('Twice a number equals eight.');
  await page.getByRole('button',{name:'Work this question'}).click();
  await expect(page.getByRole('heading',{name:'Check the interpreted inputs'})).toBeVisible();
  await expect(page.getByText('Listed calculation checks passed')).toHaveCount(0);
  await page.getByRole('button',{name:'Calculate these inputs'}).click();
  await expect(page.getByText('Listed calculation checks passed')).toBeVisible();
  await page.getByRole('button',{name:'Open source S1, PDF page 2'}).click();
  await expect(page.getByRole('link',{name:'Open original PDF'})).toHaveAttribute('href',/documents\/1\/file#page=2$/);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
