import React from 'react';
import styled from "styled-components";
import {lighten} from "polished";
import {ThemeVariables} from "../ThemeVariables";
import {CoinContract} from "./CoinContract";
import img from 'cryptocurrency-icons/32/icon/eth.png';
import {Radio} from 'semantic-ui-react';
import {BackendRoute} from "./MyCoinList";
import axios from "axios";


type Props = {
    coin: CoinContract;
    enableCoin: Function;
};

function getCoinImage(coinName: String) {
    try {
        return require(`cryptocurrency-icons/32/icon/${coinName.toLowerCase()}.png`).default
    } catch (e) {
        return img;
    }
}

function enableCoin(symbol: string, isEnabled: boolean) {

}

const Coin: React.FC<Props> = ({coin,enableCoin}: Props) => {

    return (
        <Card>
            <SymbolWrapper>
                <img alt="icon" src={getCoinImage(coin.symbol)} height={32} width={32}/>
                <CoinName>{coin.symbol}</CoinName>
            </SymbolWrapper>
            <RadioColored toggle checked={coin.enabled}
                          onChange={() => enableCoin(coin.symbol, !coin.enabled)}/>
        </Card>
    );
}

export default Coin;


const Card = styled.div`
color:white;
font-size: 1.5em;
font-family: 'Lato', 'Helvetica Neue', Arial, Helvetica, sans-serif;
  box-shadow: 0 3px 6px rgba(0,0,0,0.16), 0 3px 6px rgba(0,0,0,0.23);
  width: 28%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-right: 5%;
  margin-bottom: 2em;
  border-radius: 5px;
  padding: 1em 2em;
  background-color: ${lighten(0.04, ThemeVariables.BackgroundColor)};
`;

const CoinName = styled.h3`
  margin-top: 0;
  margin-left: 0.5em;
`;

const SymbolWrapper = styled.div`
  display: flex;
  align-items: center;
`;

const RadioColored = styled(Radio)`
  & >label::before{
    background-color: rgb(154 150 150) !important;
  }
`;
