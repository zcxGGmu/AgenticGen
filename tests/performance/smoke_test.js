import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');

export let options = {
  stages: [
    { duration: '2m', target: 10 }, // Ramp up to 10 users
    { duration: '5m', target: 10 }, // Stay at 10 users
    { duration: '2m', target: 50 }, // Ramp up to 50 users
    { duration: '5m', target: 50 }, // Stay at 50 users
    { duration: '2m', target: 0 },  // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'], // 95% of requests must be below 500ms
    http_req_failed: ['rate<0.1'],    // Error rate must be below 10%
    errors: ['rate<0.1'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:9000';

export default function() {
  // Health check
  let healthResponse = http.get(`${BASE_URL}/health`);
  let healthOk = check(healthResponse, {
    'health status is 200': (r) => r.status === 200,
    'health response time < 100ms': (r) => r.timings.duration < 100,
  });
  errorRate.add(!healthOk);

  // API documentation
  let docsResponse = http.get(`${BASE_URL}/docs`);
  let docsOk = check(docsResponse, {
    'docs status is 200': (r) => r.status === 200,
  });
  errorRate.add(!docsOk);

  // Test authentication endpoint
  let loginResponse = http.post(`${BASE_URL}/api/auth/login`, JSON.stringify({
    username: 'testuser',
    password: 'testpass'
  }), {
    headers: {
      'Content-Type': 'application/json',
    },
  });
  let loginOk = check(loginResponse, {
    'login status is 200 or 401': (r) => r.status === 200 || r.status === 401, // 401 is acceptable for invalid credentials
    'login response time < 500ms': (r) => r.timings.duration < 500,
  });
  errorRate.add(!loginOk);

  // Test metrics endpoint
  let metricsResponse = http.get(`${BASE_URL}/api/monitoring/metrics/summary`, {
    headers: {
      'Authorization': `Bearer fake_token_for_test`,
    },
  });
  let metricsOk = check(metricsResponse, {
    'metrics status is 401 or 200': (r) => r.status === 401 || r.status === 200,
    'metrics response time < 300ms': (r) => r.timings.duration < 300,
  });
  errorRate.add(!metricsOk);

  sleep(1);
}