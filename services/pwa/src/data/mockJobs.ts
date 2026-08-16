import { Job } from "../types";

export const MOCK_JOBS: Job[] = [
  {
    id: "j1",
    quoteId: "q1",
    title: "Consumer unit upgrade",
    customerName: "Jane Homeowner",
    postcode: "SK8 3NJ",
    address: "123 Demo Street, Stockport, SK8 3NJ",
    status: "confirmed",
    assignedTo: "Demo Owner",
    date: "Tue 18 Aug",
    time: "08:00 - 10:00",
    phone: "07700 123 456",
    materialCost: 180,
    labourCost: 520,
  },
  {
    id: "j2",
    quoteId: "q2",
    title: "EV charger install",
    customerName: "John Driver",
    postcode: "M20 1AA",
    address: "45 Spark Avenue, Manchester, M20 1AA",
    status: "confirmed",
    assignedTo: "Jane Engineer",
    date: "Tue 18 Aug",
    time: "13:00 - 15:00",
    phone: "07700 654 321",
    materialCost: 420,
    labourCost: 380,
  },
];
