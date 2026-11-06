try:
            inventory.hold(booking_id, seat)
            hold_success = True
        except InventoryTimeout:
            # Timeout – check if the hold actually took effect
            held = inventory.held_seat(booking_id)
            if held == seat:
                hold_success = True
            else:
                hold_success = False
