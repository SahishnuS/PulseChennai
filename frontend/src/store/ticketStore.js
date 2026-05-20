/**
 * Ticket Store — localStorage-backed ticket management
 * Key: "pulse_tickets"
 */

export function getTickets() {
  try {
    return JSON.parse(localStorage.getItem('pulse_tickets') || '[]');
  } catch {
    return [];
  }
}

export function addTicket(ticket) {
  const existing = getTickets();
  localStorage.setItem('pulse_tickets', JSON.stringify([ticket, ...existing]));
}

export function completeTicket(id) {
  const tickets = getTickets().map(t =>
    t.id === id ? { ...t, status: 'completed' } : t
  );
  localStorage.setItem('pulse_tickets', JSON.stringify(tickets));
}

export function generateTicketId() {
  return 'TKT-' + Math.random().toString(36).substring(2, 6).toUpperCase();
}
