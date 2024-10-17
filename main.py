import asyncio
import json
import csv

from rich.console import Console
from rich.table import Table
from rich.live import Live

from utils import logger
from core.grass import GrassRest

output_lock = asyncio.Lock()


class ConsoleTableFormatter:
    def __init__(self):
        self.headers = ["#", "Email", "Was", "Became", "Difference", "Bonus", "Status"]
        self.table = Table(title="Airdrop Allocation Results")
        for header in self.headers:
            self.table.add_column(header, style="cyan", justify="center")
        self.console = Console()
        self.live = Live(self.table, refresh_per_second=4)

    async def add_result(self, index, email, tokens_v2, tokens_v3, difference, bonus_epoch, status):
        self.table.add_row(str(index), email, str(tokens_v2), str(tokens_v3), str(difference), str(bonus_epoch), status, style="bright_green")

    async def start(self):
        self.live.start()

    async def stop(self):
        self.live.stop()


class AirdropAllocator:
    def __init__(self, email: str, password: str, proxy: str = None, index: int = 0):
        self.email = email
        self.password = password
        self.index = index
        self.grass_client = GrassRest(email, password, proxy)

    @staticmethod
    def calculate_totals(allocations):
        return sum(allocations.values())

    @staticmethod
    def get_bonus_epoch(allocations):
        bonus_epoch = 0
        for key, value in allocations.items():
            if key.startswith('bonusepoch_'):
                bonus_epoch += value
        return bonus_epoch

    @staticmethod
    def beautify_and_log(data, log_filename='airdrop_log.json'):
        with open(log_filename, 'a') as log_file:
            json.dump(data, log_file, indent=4)
            log_file.write('\n')

    def save_to_csv(self, data, filename='airdrop_allocation.csv'):
        with open(filename, mode='a', newline='') as file:
            csv.writer(file).writerow([
                self.email,
                data['total_v2'],
                data['total_v3'],
                data['difference'],
                data['bonus_epoch'],
                data['wallet_address']
            ])

    async def process_allocation(self, table_formatter, log_filename='airdrop_log.json'):
        try:
            await self.grass_client.enter_account()
            user_data = await self.grass_client.retrieve_user()
            
            allocations_v2 = user_data['result']['data']['allocationsV2']
            allocations_v3 = user_data['result']['data']['allocationsV3']
            
            total_v2 = self.calculate_totals(allocations_v2)
            total_v3 = self.calculate_totals(allocations_v3)
            difference = total_v3 - total_v2
            bonus_epoch = self.get_bonus_epoch(allocations_v3)

            status = "Eligible"
            if any('_sybil' in key for key in allocations_v3):
                status = "Sybil"

            wallet_address = user_data['result']['data']['walletAddress']
            
            data = {
                'email': self.email,
                'total_v2': round(total_v2, 2),
                'total_v3': round(total_v3, 2),
                'difference': round(difference, 2),
                'bonus_epoch': round(bonus_epoch, 2),
                'status': status,
                'wallet_address': wallet_address
            }

            await table_formatter.add_result(
                self.index, self.email, data['total_v2'], data['total_v3'], data['difference'], data['bonus_epoch'], status
            )
            
            self.beautify_and_log(user_data, log_filename)
            self.save_to_csv(data)

            with open(f"logs/{status.lower()}s.txt", "a") as f:
                f.write(f"{self.email},{wallet_address}\n")

            return data

        except Exception as e:
            logger.error(f"Error processing allocation for {self.email}: {str(e)}")
            await table_formatter.add_result(self.index, self.email, 0, 0, 0, 0, "Error")
            return None
        finally:
            await self.grass_client.close()


async def read_file_lines(file_path):
    with open(file_path, 'r') as file:
        return [line.strip() for line in file if line.strip()]


async def main():
    accounts = await read_file_lines('data/accounts.txt')
    accounts = [account.split(':') for account in accounts]

    if not accounts:
        logger.info("No accounts found!")
        return

    proxies = await read_file_lines('data/proxies.txt')
    table_formatter = ConsoleTableFormatter()

    await table_formatter.start()

    tasks = [
        AirdropAllocator(
            email, 
            password, 
            proxies[i % len(proxies)] if proxies else None, 
            i+1
        ).process_allocation(table_formatter)
        for i, (email, password) in enumerate(accounts)
    ]

    results = await asyncio.gather(*tasks)
    await table_formatter.stop()

    total_v2 = sum(result['total_v2'] for result in results if result)
    total_v3 = sum(result['total_v3'] for result in results if result)
    total_difference = sum(result['difference'] for result in results if result)

    token_price = 1.5

    console = Console()
    console.print("\n\nHope for token price is 1.5$.", style="bold yellow")
    console.print("Total Results ($GRASS):", style="bold green")
    console.print(f"Total was: {total_v2:.2f}", style="cyan")
    console.print(f"Total final preview: {total_v3:.2f}", style="cyan")
    console.print(f"Total Difference: {total_difference:.2f}", style="cyan")

    console.print("\nTotal Results (USD):", style="bold green")
    console.print(f"Total was: ${total_v2 * token_price:.2f}", style="cyan")
    console.print(f"Total final preview: ${total_v3 * token_price:.2f}", style="cyan")
    console.print(f"Total Difference: ${total_difference * token_price:.2f}\n", style="cyan")

    logger.success(f"Airdrop allocation check completed. You will get {total_v3 * token_price:.2f} $")


if __name__ == '__main__':
    console = Console()
    console.print("Starting Airdrop Allocator...", style="bold green")
    console.print("IF ERRORS OCCUR - CHANGE PROXY OR ACCOUNT IS INVALID OR UNELIGIBLE\n", style="bold yellow")

    asyncio.run(main())
