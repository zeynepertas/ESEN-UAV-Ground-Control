import { ApplicationConfig } from '@angular/core';
import { provideRouter } from '@angular/router';
import { routes } from './app.routes';
import { provideHttpClient } from '@angular/common/http'; // BURASI EKLENDİ

export const appConfig: ApplicationConfig = {
  // provideHttpClient() kısmını providers listesine ekledik
  providers: [provideRouter(routes), provideHttpClient()] 
};