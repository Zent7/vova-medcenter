import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../public/demo/app.js", import.meta.url), "utf8");
function createContext({failSync = false} = {}) {
  const exam = {id:"exam-123", clientId:7, visitId:"encounter-8", doctorRoleId:"chairman", fields:{doctor:"Сибирцев В. А."}, isCompleted:false};
  const synced = [];
  const context = vm.createContext({
    data: {doctorExams:[exam], visits:[{id:"encounter-8"}]},
    appState: {doctorExamModal:{isOpen:true,clientId:7,visitId:"encounter-8",doctorRoleId:"chairman"}},
    ensureVisitsStore() {}, rememberMkb10Value() {}, persistDemoState() {}, renderApp() {}, showToast() {},
    console:{warn() {}},
    getDoctorExam(clientId,visitId,role) {return context.data.doctorExams.find(item => item.clientId===clientId && item.visitId===visitId && item.doctorRoleId===role);},
    async syncDoctorExamToBackend(item) {if (failSync) throw new Error("Сервер недоступен"); synced.push(item);},
    async syncChairmanExamToClientAndMedicalRecord() {}, async refreshDashboardDoctorStatusForExam() {},
  });
  vm.runInContext(source.slice(source.indexOf("async function saveDoctorExam("),source.indexOf("async function deleteDoctorExam(")),context);
  return {context,exam,synced};
}

test("printing saves a chairman exam after the server replaced its temporary id", async () => {
  const {context,exam,synced}=createContext();
  assert.equal(await context.saveDoctorExam("exam-local-draft",{conclusion:"Годен"},{doctorRoleId:"chairman",waitForSecondarySync:false}),true);
  assert.equal(synced[0],exam);
  assert.equal(exam.fields.conclusion,"Годен");
});

test("stale id resolution cannot save a different specialty", async () => {
  const {context,synced}=createContext();
  assert.equal(await context.saveDoctorExam("exam-local-draft",{conclusion:"Годен"},{doctorRoleId:"therapist"}),false);
  assert.equal(synced.length,0);
});

test("print caller receives the actual server error and fields roll back", async () => {
  const {context,exam}=createContext({failSync:true});
  await assert.rejects(context.saveDoctorExam("exam-123",{conclusion:"Годен"},{throwOnError:true}),/Сервер недоступен/);
  assert.equal(exam.fields.conclusion,undefined);
  assert.equal(exam.isCompleted,false);
  assert.equal(exam.__saving,false);
});

test("071 print handler recovers the stale form id and opens the correct print flow", async () => {
  const {context,exam,synced}=createContext();
  const flows=[];
  Object.assign(context, {
    chairmanForm:{dataset:{examId:"exam-local-draft"}},
    collectChairmanModalFormValues:()=>({conclusion:"Годен"}),
    humanizeApiError:error=>error.message,
    showDocumentTargetError:(_window,message)=>{throw new Error(message);},
    getClientPool:()=>[{id:7}],
    getChairmanTemplatePrintType:()=>"071",
    getChairmanFormInfo:()=>({type:"tractor",printMode:"document"}),
    opensNumberedCertificatePrintWindow:()=>true,
    getChairmanNumberedCertificateSeries:()=>"071у",
    chairmanPrintBlankState:{selectedSeries:"071у",blanks:new Map()},
    window:{saveDoctorExam:context.saveDoctorExam,closeDoctorExamCard(){},async openDriverPrintFlow(options){flows.push(options);}},
  });
  const start=source.indexOf("const runChairmanPrint = async");
  const end=source.indexOf('    printButton.addEventListener("click"',start);
  vm.runInContext(source.slice(start,end)+"\nthis.print071 = runChairmanPrint;",context);
  await context.print071("071_certificate","071",{disabled:false},{closed:false,close(){this.closed=true;}});
  assert.equal(context.chairmanForm.dataset.examId,exam.id);
  assert.equal(synced[0],exam);
  assert.equal(flows[0].selectedCertificateType,"071");
});
