import {emptyRecordState,applyRecord,commonBase,stageRecordPage} from '../../../packages/sync-protocol/src/record-kernel-core';
// Dedicated synthetic harness bundle; never imported by the normal B/PC apps.
Object.assign(window,{recordKernel:{emptyRecordState,applyRecord,commonBase,stageRecordPage}});
