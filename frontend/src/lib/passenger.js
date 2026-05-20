export function getPassengerId() {
  let passengerId = window.localStorage.getItem('pulse_passenger_id');
  if (!passengerId) {
    passengerId = 'user_' + Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
    window.localStorage.setItem('pulse_passenger_id', passengerId);
  }
  return passengerId;
}
