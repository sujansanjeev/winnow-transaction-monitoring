# Winnow Transaction Monitoring

Winnow Transaction Monitoring is a transaction monitoring system designed to detect and flag suspicious activities based on predefined conditions.

## Features

- Monitors transactions in real-time
- Raises alerts based on specific conditions:
  - A customer making 3 or more transactions
  - A transaction amount greater than 55,000
  - A single transaction of exactly 55,000
- Displays alerts alongside transaction data in the UI

## Installation

### Prerequisites

- Python 3.8+
- Flask
- Sqlite

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/sujansanjeev/winnow-transaction-monitoring.git
   cd winnow-transaction-monitoring
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python app.py
   ```
4. Access the app in your browser at `http://localhost:5000`.

## Usage

- Upload transaction data via the `uploads` folder.
- View transactions and alerts on the dashboard.
- Modify `app.py` to adjust alert conditions if needed.

## Contributing

Feel free to submit issues or pull requests to improve the project.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

