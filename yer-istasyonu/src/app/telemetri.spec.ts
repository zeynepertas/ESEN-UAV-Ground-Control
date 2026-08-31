import { TestBed } from '@angular/core/testing';

import { TelemetriService } from './telemetri';

describe('TelemetriService', () => {
  let service: TelemetriService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(TelemetriService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
